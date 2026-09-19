# Экспериментальные характеристики: обороты, напряжение, мощность

**Экспериментальный безмагнитный аутраннер на базе Dualsky 3520C V2**

Ревизия: Прототип, испытания 2026-09-12 и 2026-09-13

**Полный паспорт НЕ ЗАВЕРШЁН. Сейчас собираются только доступные данные VESC; номинальный и предельный режимы не установлены.**

## Конструкция со слов изготовителя

- Ротор без постоянных силовых магнитов; материал сегментов — сталь 20.
- Трёхфазная обмотка соединена треугольником.
- Число витков сохранено со слов изготовителя; точное значение не записано.
- Параллельные жилы диаметром около 0,15 мм; точное число жил пока неизвестно.
- Исходный мотор указан как Dualsky 3520C kv510 V2; KV510 не является характеристикой переделанного мотора.
- Источник питания испытаний 2026-09-13: аккумулятор 6S1P, 4500 мА·ч. Химия, допустимые токи и напряжения отдельных ячеек не подтверждены.

## Инженерная интерпретация

- Рабочая классификация: синхронный реактивный двигатель с внешним ротором (SynRM).
- По схеме обмотки: 12 пазов, основная пространственная гармоника 4 полюса / 2 пары; конфигурация использует ratio=2.
- По предоставленному чертежу ротора: диаметры 36/40,3 мм, длина 21 мм, четыре винтовые прорези, скос 26 градусов. Это размеры чертежа, не обмер готового двигателя.
- AS5048A используется напрямую по SPI; его отдельный магнит положения не является силовым магнитом ротора.

## Проверенные стендовые наблюдения

Контроллер MKSESC_84_100_HP, firmware 6.02; управление внешней программой через USB.
Нет измеренного момента нагрузки. Скорость получена из угла AS5048A; точность независимым прибором не аттестована.
Ограничения тока относятся к конкретным испытаниям, а не к номиналу мотора. Ток Id/Iq не равен току батареи или измеренному току ветви треугольника.

| Прогон | Время, с | Средние обороты | Диапазон оборотов | DC-шина, В | Оценка входной мощности VESC, Вт |
| --- | ---: | ---: | --- | ---: | ---: |
| [synrm-speed-540rpm-5a-smooth-20260912-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-540rpm-5a-smooth-20260912-01/result.json) | 23.81 | 462.5 | 460.4–464.2 | 24.7 | 0.95 |
| [synrm-speed-540rpm-5a-smooth-20260912-02](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-540rpm-5a-smooth-20260912-02/result.json) | 23.80 | 462.1 | 458.3–465.4 | 24.7 | 0.95 |
| [synrm-speed-600rpm-5a-smooth-20260912-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-600rpm-5a-smooth-20260912-01/result.json) | 23.80 | 512.6 | 509.8–515.3 | 24.7 | 0.99 |
| [synrm-speed-660rpm-5a-smooth-20260912-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-660rpm-5a-smooth-20260912-01/result.json) | 23.80 | 564.0 | 560.9–566.6 | 24.6 | 0.98 |
| [synrm-speed-700rpm-5a-smooth-20260912-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-700rpm-5a-smooth-20260912-01/result.json) | 23.80 | 590.8 | 583.9–599.5 | 24.6 | 0.99 |
| [synrm-speed-700rpm-5a-upper-20260912-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-700rpm-5a-upper-20260912-01/result.json) | 23.80 | 637.9 | 634.1–641.1 | 24.6 | 1.02 |
| [synrm-speed-1200rpm-5a-smooth-20260912-02](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-1200rpm-5a-smooth-20260912-02/result.json) | 23.80 | 1048.2 | 1042.7–1053.4 | 24.5 | 1.47 |
| [synrm-speed-1700rpm-5a-smooth-20260912-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-1700rpm-5a-smooth-20260912-01/result.json) | 23.80 | 1437.6 | 1426.8–1445.6 | 24.5 | 1.79 |
| [synrm-speed-2200rpm-5a-hold-20260912-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-2200rpm-5a-hold-20260912-01/result.json) | 39.80 | 1816.0 | 1807.7–1824.4 | 24.5 | 2.10 |
| [synrm-speed-2200rpm-5a-counter-20260913-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-2200rpm-5a-counter-20260913-01/result.json) | 39.80 | 1820.6 | 1814.5–1827.7 | 24.5 | 2.05 |
| [synrm-speed-2700rpm-6a-return-coast-20260913-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-2700rpm-6a-return-coast-20260913-01/result.json) | 39.80 | 2353.3 | 2350.1–2356.2 | 24.5 | 2.45 |
| [synrm-speed-3200rpm-7a-return-coast-20260913-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-3200rpm-7a-return-coast-20260913-01/result.json) | 39.80 | 2895.8 | 2889.1–2903.0 | 24.5 | 2.53 |
| [synrm-speed-3700rpm-7a-return-coast-20260913-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-3700rpm-7a-return-coast-20260913-01/result.json) | 39.80 | 3374.9 | 3366.1–3381.2 | 24.5 | 2.89 |
| [synrm-speed-4200rpm-7a-return-coast-20260913-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-4200rpm-7a-return-coast-20260913-01/result.json) | 39.80 | 3854.2 | 3849.4–3859.2 | 24.4 | 3.17 |
| [synrm-speed-4700rpm-7a-reacquire-20260913-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-4700rpm-7a-reacquire-20260913-01/result.json) | 39.80 | 4339.6 | 4330.5–4350.1 | 24.4 | 3.42 |
| [synrm-speed-5200rpm-7a-hold60-20260913-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-5200rpm-7a-hold60-20260913-01/result.json) | 59.80 | 4821.8 | 4815.8–4828.4 | 24.4 | 3.68 |
| [synrm-speed-5700rpm-8a-hold60-20260913-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-5700rpm-8a-hold60-20260913-01/result.json) | 59.80 | 5351.6 | 5344.6–5358.7 | 24.4 | 4.14 |
| [synrm-speed-6200rpm-8a-hold60-20260913-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-6200rpm-8a-hold60-20260913-01/result.json) | 59.80 | 5829.6 | 5821.7–5837.4 | 24.4 | 4.59 |
| [synrm-speed-6200rpm-8a-native60-20260913-03](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-6200rpm-8a-native60-20260913-03/result.json) | 59.81 | 5831.7 | 5825.3–5837.4 | 24.2 | 4.51 |
| [synrm-speed-6700rpm-8a-native60-20260913-01](C:/Users/jando/Desktop/Codex/2026-08-11/e-d/outputs/logs/synrm-speed-6700rpm-8a-native60-20260913-01/result.json) | 59.81 | 6309.1 | 6303.2–6315.1 | 24.2 | 5.00 |

Хеши исходных файлов и расширенные показатели: `motor-passport-draft.json` рядом с этим документом.
Средние значения рассчитаны с весом по времени на последних пяти секундах. Мощность: среднее Udc·Iin по отсчётам, а не произведение двух средних. Напряжение относится к DC-шине, не к фазам мотора.
Это оценка входной мощности VESC, не механическая мощность. В зависимости от аппаратной реализации ток может вычисляться из фазных токов и модуляции; потребление вспомогательной электроники не проверено. Внешней калибровки нет.
Шаг кодирования входного тока 0,01 А, напряжения 0,1 В. При 24,7 В шаг тока соответствует примерно 0,25 Вт в отдельном отсчёте. Усреднение не устраняет систематическую погрешность; две цифры после запятой не означают такую точность.
Устойчивость подтверждена только по критерию данного прогона. Это не точность слежения за заданной скоростью и не гарантия запуска под нагрузкой.
Результат проверки влияния программного ограничения записан в JSON. Установившаяся скорость при активном снижении тока не является найденной максимальной скоростью мотора; допустимый механический предел не установлен.
Проверенные профили используют нулевой постоянномагнитный поток как модель и предварительный offset 1,020427465°. Одного переноса бинарной конфигурации без программы управления недостаточно.

## Номинальные данные

Напряжение, ток, момент, мощность, номинальные и максимально допустимые обороты, КПД, рабочий цикл, класс изоляции и температурный подъём **не определены**.
Настройки R/L и offset сохранены в JSON отдельно: они не выдаются за аттестованные параметры двигателя.

## Отложенная часть полного паспорта

По решению пользователя внешней оснастки пока нет: момент, КПД, длительный номинал и прочие недоступные характеристики сейчас не собираются. Перечень остаётся в JSON и программе испытаний, но не блокирует сбор оборотов, DC-напряжения и оценки входной мощности.

## Границы измерений

Механическая мощность рассчитывается только при измеренном моменте: Pвал = 2π·n·M/60.
Отношение Pвал к мощности DC-входа характеризует выбранную границу привода вместе с потерями контроллера. Для КПД самого мотора нужна электрическая мощность на его входе; ток и duty её не заменяют.
Для длительного номинала нужен проверенный температурный канал обмотки. Нынешние отрицательные значения датчика недостоверны.

## Методические ориентиры

[IEC 60034-1:2026](https://webstore.iec.ch/en/publication/89961): номинальные данные и характеристики вращающихся машин.
[IEC 60034-2-3:2024](https://webstore.iec.ch/en/publication/67758): испытания потерь и КПД двигателей с питанием от преобразователя.
Использованы открытые описания областей применения; соответствие стандартам не заявляется. Полную методику и применимость к назначению изделия нужно согласовать отдельно.

## Непринятые или ещё не выполненные прогоны

- logs/synrm-speed-540rpm-5a-20260912-01: Next speed step requires a qualified speed_540rpm_5a trial
- logs/synrm-speed-1200rpm-5a-smooth-20260912-01: Next speed step requires a qualified speed_1200rpm_5a_smooth trial
- logs/synrm-speed-2200rpm-5a-smooth-20260912-01: Next speed step requires a qualified speed_2200rpm_5a_smooth trial
- logs/synrm-speed-2200rpm-5a-smooth-20260912-02: Next speed step requires a qualified speed_2200rpm_5a_smooth trial
- logs/synrm-speed-2200rpm-5a-smooth-20260912-03: Next speed step requires a qualified speed_2200rpm_5a_smooth trial
- logs/synrm-counter-validation-2200-20260913-01: Next speed step requires a qualified speed_2200rpm_5a_hold trial
- logs/synrm-speed-2700rpm-5a-counter-20260913-01: Next speed step requires a qualified speed_2700rpm_5a_counter trial
- logs/synrm-speed-2700rpm-6a-counter-20260913-01: Next speed step requires a qualified speed_2700rpm_6a_counter trial
- logs/synrm-speed-2700rpm-6a-return-20260913-01: Next speed step requires a qualified speed_2700rpm_6a_counter_return trial
- logs/synrm-speed-4700rpm-7a-return-coast-20260913-01: Next speed step requires a qualified speed_4700rpm_7a_counter_return_coast trial
- logs/synrm-speed-5200rpm-7a-reacquire-20260913-01: Next speed step requires a qualified speed_5200rpm_7a_coast_reacquire trial
- logs/synrm-speed-6200rpm-8a-native60-20260913-01: Completed memory log drainage required
- logs/synrm-speed-6200rpm-8a-native60-20260913-02: [Errno 2] No such file or directory: 'C:\\Users\\jando\\Desktop\\Codex\\2026-08-11\\e-d\\outputs\\logs\\synrm-speed-6200rpm-8a-native60-20260913-02\\final-readback.json'
- logs/synrm-speed-7200rpm-8a-native60-20260913-01: Next speed step requires a qualified speed_7200rpm_8a_native60 trial
