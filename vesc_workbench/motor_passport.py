"""Evidence-backed draft passport. Offline only; no controller commands."""
import hashlib
import json
import math
from pathlib import Path

from .synrm_pilot import speed_stability, stage_limits
from .synrm_pilot_runner import audit_speed_run
from .wire_config import decode_config


MISSING = {
    'identity_dimensions': 'Серийный номер, ревизия ротора/обмотки, масса, габариты, вал, крепления и подшипники: обмер и ведомость сборки.',
    'winding': 'Точное число витков и жил, диаметр меди без эмали, схема выводов, изоляционные материалы: запись изготовителя.',
    'electrical': 'Межлинейные сопротивления при известной температуре, симметрия фаз, карта Ld/Lq по углу и току: отдельные измерения. Значения конфигурации не заменяют их.',
    'encoder': 'Проверка масштаба и направления независимым тахометром; глобальная калибровка offset пока не завершена.',
    'startup': 'Покрытие начальных углов, обоих направлений и заданной нагрузки. Два старта без заданного момента не доказывают гарантированный старт.',
    'speed_envelope': 'Минимальная устойчивая и максимальная допустимая скорость, повторяемость скоростных ступеней; верхняя испытанная точка не является механическим пределом.',
    'torque_power': 'Момент и механическая мощность на валу в точках скорости/нагрузки: калиброванный датчик момента и измерение оборотов.',
    'efficiency': 'КПД двигателя либо привода с явно указанной границей: синхронные измерения механической и электрической мощности.',
    'thermal_rating': 'Проверенный датчик температуры обмотки, температура окружающей среды, охлаждение и длительные нагрузочные испытания для назначения номинала и режима работы.',
    'mechanical_insulation': 'Балансировка, вибрация, удержание сегментов, изоляция и электрическая прочность: отдельная программа с подходящими приборами; не через подключённый ESC.',
    'service': 'Назначение, условия среды, охлаждение, ресурс, обслуживание, ограничения эксплуатации и критерии приёмки: согласовать с изготовителем.'
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dc_window_statistics(rows):
    """Right-endpoint, time-weighted telemetry estimates, not shaft power."""
    keys = ('t', 'encoder_rpm', 'v_in', 'current_in_a')
    if len(rows) < 2 or any(not math.isfinite(r[k]) for r in rows for k in keys):
        raise ValueError('Missing or nonfinite DC-window telemetry')
    dt = [b['t']-a['t'] for a, b in zip(rows, rows[1:])]
    if min(dt) <= 0:
        raise ValueError('Nonmonotonic DC-window telemetry')
    def mean(fn):
        return sum(fn(r)*d for r, d in zip(rows[1:], dt))/sum(dt)
    powers = [r['v_in']*r['current_in_a'] for r in rows]
    return dict(duration_s=sum(dt), samples=len(rows),
                mean_rpm=mean(lambda r: r['encoder_rpm']),
                mean_voltage_v=mean(lambda r: r['v_in']),
                mean_input_current_a=mean(lambda r: r['current_in_a']),
                mean_input_power_w_estimate=mean(lambda r: r['v_in']*r['current_in_a']),
                minimum_power_w=min(powers), maximum_power_w=max(powers),
                minimum_voltage_v=min(r['v_in'] for r in rows), maximum_voltage_v=max(r['v_in'] for r in rows),
                current_encoding_step_a=.01, voltage_encoding_step_v=.1,
                external_calibration=False, shaft_power_w=None,
                interpretation='VESC DC-input estimate; firmware-dependent current acquisition; auxiliary consumption not verified')


def speed_limit_assessment(rows, stage):
    """Distinguish a host-governed plateau from evidence of a motor maximum."""
    limits = stage_limits(stage)
    dc_window_statistics(rows)
    if any(not math.isfinite(r['command_a']) or not 0 <= r['command_a'] <= limits['current'] for r in rows):
        raise ValueError('Invalid command in speed-limit evidence')
    dt = [b['t']-a['t'] for a, b in zip(rows, rows[1:])]
    taper_time = sum(d for r, d in zip(rows[1:], dt)
                     if r['encoder_rpm'] >= limits['taper_start_rpm'] and r['command_a'] < .95*limits['current'])
    return dict(maximum_speed_established=False,
                host_taper_time_fraction=taper_time/sum(dt),
                classification='host_taper_limited' if taper_time/sum(dt) >= .9 else 'maximum_not_established',
                command_limit_a=limits['current'], cutoff_rpm=limits['cutoff_rpm'],
                software_guard_rpm=limits['maximum_rpm'], mechanical_rating_rpm=None)


def summarize_run(folder, baseline, stage):
    folder = Path(folder)
    audit_speed_run(folder, baseline, stage)
    report = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    rows = [json.loads(line) for line in (folder/'observations.jsonl').read_text(encoding='utf-8').splitlines()]
    tail = [r for r in rows if r['t'] >= rows[-1]['t']-5]
    stability = speed_stability([(r['t'], r['encoder_rpm']) for r in tail], stage)
    times = [r['t'] for r in tail]
    dt = [b-a for a, b in zip(times, times[1:])]
    if not dt or min(dt) <= 0:
        raise ValueError('Missing ordered final-window samples')
    def mean(fn):
        return sum(fn(r)*d for r, d in zip(tail[1:], dt))/sum(dt)
    norms = [math.hypot(r['id_a'], r['iq_a']) for r in rows]
    files = ('result.json', 'observations.jsonl', 'samples.jsonl', 'final-readback.json',
             'mcconf-before.bin', 'mcconf-candidate.bin')
    return dict(path=str(folder.resolve()), stage=stage, evidence_verified=True,
                measurement_method=report.get('measurement_method', 'short_gap_absolute_encoder_receive_time_window'),
                hashes={name: sha((folder/name).read_bytes()) for name in files},
                candidate_sha256=report['plan']['candidate_sha256'],
                powered_s=rows[-1]['elapsed_s'], turns=rows[-1]['travel_deg']/360,
                peak_rpm=max(r['encoder_rpm'] for r in rows), stability=stability,
                command_peak_a=max(r['command_a'] for r in rows), measured_dq_norm_peak_a=max(norms),
                final_mean_dq_norm_a=mean(lambda r: math.hypot(r['id_a'], r['iq_a'])),
                final_mean_dc_voltage_v=mean(lambda r: r['v_in']),
                final_mean_dc_input_w_estimate=mean(lambda r: r['v_in']*r['current_in_a']),
                dc_window=dc_window_statistics(tail),
                speed_limit_assessment=speed_limit_assessment(tail, stage),
                first_3deg_s=next((r['elapsed_s'] for r in rows if r['travel_deg'] >= 3), None),
                start_reference_deg=report['expected_start_pose_deg'],
                input_energy_j=rows[-1]['input_energy_j'], i2t_a2s=rows[-1]['i2t_a2s'],
                interpretation='Bounded bench observation; not a nameplate rating or motor-only efficiency')


def build_passport(manifest, root):
    root = Path(root)
    if manifest['schema'] != 'motor-passport-input-v1':
        raise ValueError('Unsupported passport schema')
    baseline = (root/manifest['baseline']).read_bytes()
    if sha(baseline) != manifest['baseline_sha256']:
        raise ValueError('Passport baseline digest mismatch')
    runs, excluded = [], []
    for item in manifest['runs']:
        try:
            runs.append(summarize_run(root/item['path'], baseline, item['stage']))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            excluded.append(dict(path=item['path'], reason=str(exc)))
    values = decode_config(baseline, 'motor')
    keys = ('foc_motor_r', 'foc_motor_l', 'foc_motor_ld_lq_diff', 'foc_encoder_ratio', 'foc_encoder_offset')
    return dict(schema='motor-passport-draft-v1', status='incomplete_not_for_rated_operation',
                current_scope='rpm_voltage_and_vesc_input_power_only',
                specimen=manifest['specimen'], revision=manifest['revision'],
                user_reported=manifest['user_reported'], engineering_interpretation=manifest['engineering_interpretation'],
                verified_runs=runs, excluded_runs=excluded, missing=MISSING,
                baseline_settings_not_motor_ratings={k: values[k] for k in keys},
                rated_voltage_v=None, rated_current_a=None, rated_power_w=None,
                rated_torque_nm=None, rated_speed_rpm=None, maximum_permitted_rpm=None,
                motor_efficiency=None, drive_efficiency=None, duty_type=None,
                temperature_rise_k=None, measurement_uncertainty=None,
                automatic_excitation=False)


def render_markdown(data):
    lines = ['# Экспериментальные характеристики: обороты, напряжение, мощность', '', f"**{data['specimen']}**", '',
             f"Ревизия: {data['revision']}", '',
             '**Полный паспорт НЕ ЗАВЕРШЁН. Сейчас собираются только доступные данные VESC; номинальный и предельный режимы не установлены.**', '',
             '## Конструкция со слов изготовителя', '']
    lines += ['- '+v for v in data['user_reported']]
    lines += ['', '## Инженерная интерпретация', '']
    lines += ['- '+v for v in data['engineering_interpretation']]
    lines += ['', '## Проверенные стендовые наблюдения', '',
              'Контроллер MKSESC_84_100_HP, firmware 6.02; управление внешней программой через USB.',
              'Нет измеренного момента нагрузки. Скорость получена из угла AS5048A; точность независимым прибором не аттестована.',
              'Ограничения тока относятся к конкретным испытаниям, а не к номиналу мотора. Ток Id/Iq не равен току батареи или измеренному току ветви треугольника.', '',
              '| Прогон | Время, с | Средние обороты | Диапазон оборотов | DC-шина, В | Оценка входной мощности VESC, Вт |',
              '| --- | ---: | ---: | --- | ---: | ---: |']
    for r in data['verified_runs']:
        s = r['stability']
        dc = r['dc_window']
        lines.append(f"| [{Path(r['path']).name}]({Path(r['path']).as_posix()}/result.json) | {r['powered_s']:.2f} | {dc['mean_rpm']:.1f} | {s['minimum_rpm']:.1f}–{s['maximum_rpm']:.1f} | {dc['mean_voltage_v']:.1f} | {dc['mean_input_power_w_estimate']:.2f} |")
    lines += ['', 'Хеши исходных файлов и расширенные показатели: `motor-passport-draft.json` рядом с этим документом.',
              'Средние значения рассчитаны с весом по времени на последних пяти секундах. Мощность: среднее Udc·Iin по отсчётам, а не произведение двух средних. Напряжение относится к DC-шине, не к фазам мотора.',
              'Это оценка входной мощности VESC, не механическая мощность. В зависимости от аппаратной реализации ток может вычисляться из фазных токов и модуляции; потребление вспомогательной электроники не проверено. Внешней калибровки нет.',
              'Шаг кодирования входного тока 0,01 А, напряжения 0,1 В. При 24,7 В шаг тока соответствует примерно 0,25 Вт в отдельном отсчёте. Усреднение не устраняет систематическую погрешность; две цифры после запятой не означают такую точность.',
              'Устойчивость подтверждена только по критерию данного прогона. Это не точность слежения за заданной скоростью и не гарантия запуска под нагрузкой.',
              'Результат проверки влияния программного ограничения записан в JSON. Установившаяся скорость при активном снижении тока не является найденной максимальной скоростью мотора; допустимый механический предел не установлен.',
              'Проверенные профили используют нулевой постоянномагнитный поток как модель и предварительный offset 1,020427465°. Одного переноса бинарной конфигурации без программы управления недостаточно.', '',
              '## Номинальные данные', '',
              'Напряжение, ток, момент, мощность, номинальные и максимально допустимые обороты, КПД, рабочий цикл, класс изоляции и температурный подъём **не определены**.',
              'Настройки R/L и offset сохранены в JSON отдельно: они не выдаются за аттестованные параметры двигателя.', '',
              '## Отложенная часть полного паспорта', '',
              'По решению пользователя внешней оснастки пока нет: момент, КПД, длительный номинал и прочие недоступные характеристики сейчас не собираются. Перечень остаётся в JSON и программе испытаний, но не блокирует сбор оборотов, DC-напряжения и оценки входной мощности.']
    lines += ['', '## Границы измерений', '',
              'Механическая мощность рассчитывается только при измеренном моменте: Pвал = 2π·n·M/60.',
              'Отношение Pвал к мощности DC-входа характеризует выбранную границу привода вместе с потерями контроллера. Для КПД самого мотора нужна электрическая мощность на его входе; ток и duty её не заменяют.',
              'Для длительного номинала нужен проверенный температурный канал обмотки. Нынешние отрицательные значения датчика недостоверны.', '',
              '## Методические ориентиры', '',
              '[IEC 60034-1:2026](https://webstore.iec.ch/en/publication/89961): номинальные данные и характеристики вращающихся машин.',
              '[IEC 60034-2-3:2024](https://webstore.iec.ch/en/publication/67758): испытания потерь и КПД двигателей с питанием от преобразователя.',
              'Использованы открытые описания областей применения; соответствие стандартам не заявляется. Полную методику и применимость к назначению изделия нужно согласовать отдельно.', '',
              '## Непринятые или ещё не выполненные прогоны', '']
    lines += [f"- {r['path']}: {r['reason']}" for r in data['excluded_runs']] or ['Нет.']
    return '\n'.join(lines)+'\n'
