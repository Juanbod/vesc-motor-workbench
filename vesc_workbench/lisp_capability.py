"""Read-only Lisp storage/runtime queries from the pinned VESC 6.02 protocol."""
from struct import unpack

from .uart import VescPacketError


def read_lisp_capability(client):
    result = dict(excitation_sent=False, configuration_writes=False, code_writes=False,
                  runtime_started=False, protocol_reference='f7c2b34e1cff2234cae98be3abf0cd50e249558f',
                  stored_code_bytes=None, runtime_response=False, errors=[])
    # READ_CODE with zero requested bytes only returns the storage header.
    client.send_payload(bytes((130,))+bytes(8))
    try:
        payload = client.read_response(130)
        if len(payload) != 9 or payload[0] != 130:
            raise ValueError('Invalid Lisp storage header')
        length, offset = unpack('>ii', payload[1:])
        if length < 0 or offset != 0:
            raise ValueError('Invalid Lisp storage length/offset')
        result['stored_code_bytes'] = length
        result['storage_header_hex'] = payload.hex()
    except (VescPacketError, ValueError) as exc:
        result['errors'].append(str(exc))
    client.send_payload(bytes((134,)))
    try:
        payload = client.read_response(134)
        if len(payload) < 10 or payload[0] != 134:
            raise ValueError('Invalid Lisp runtime statistics')
        result['runtime_response'] = True
        result['runtime_stats_hex'] = payload.hex()
    except (VescPacketError, ValueError) as exc:
        result['errors'].append(str(exc))
    result['interpretation'] = ('Runtime replied; no program was started or replaced'
                                if result['runtime_response'] else
                                'No runtime reply: inactive runtime or unsupported build; absence alone is inconclusive')
    return result


def probe_empty_lisp_arithmetic(client, capability):
    """One literal RAM expression; may initialize an empty interpreter, never torque."""
    if capability.get('stored_code_bytes') != 0 or capability.get('runtime_response') is not False:
        raise ValueError('Arithmetic probe requires confirmed empty storage and no active runtime reply')
    result = dict(expression='(+ 1 2)', ram_expression_sent=False, flash_writes=False,
                  excitation_sent=False, configuration_writes=False, runtime_start_may_be_requested=True,
                  arithmetic_verified=False, lines=[], errors=[])
    client.send_payload(bytes((138,))+b'(+ 1 2)\0')
    result['ram_expression_sent'] = True
    for _ in range(16):
        try:
            payload = client.read_response(135)
        except VescPacketError as exc:
            result['errors'].append(str(exc))
            break
        if not payload or payload[0] != 135:
            raise ValueError('Unexpected Lisp print packet')
        line = payload[1:].decode('utf-8', errors='replace').strip('\0\r\n ')
        result['lines'].append(line)
        if line == '> 3':
            result['arithmetic_verified'] = True
            break
    return result


def read_native_snapshot(client):
    """Fixed read-only expression, no definitions, loops or motor commands."""
    expression = b'(list (systime) (get-encoder) (systime) (get-rpm) (get-id) (get-iq) (get-vin))'
    client.send_payload(bytes((138,))+expression+b'\0')
    for _ in range(16):
        payload = client.read_response(135)
        if not payload or payload[0] != 135:
            raise ValueError('Unexpected Lisp print packet')
        line = payload[1:].decode('utf-8', errors='replace').strip('\0\r\n ')
        if line.startswith('> '):
            return dict(expression=expression.decode('ascii'), result_text=line,
                        excitation_sent=False, configuration_writes=False, flash_writes=False)
    raise ValueError('No native snapshot result')
