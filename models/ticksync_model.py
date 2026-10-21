#!/usr/bin/env python3
"""
Модель алгоритма Tick Sync по его исходникам — чтобы цифры в видео были не «в идеале», а как у настоящего мода.

Исходник: github.com/LogGamja/tick-sync-1.21.5, коммит d0ae181, файл TickSyncMain.java.
Запуск: python models/ticksync_model.py (нужен только numpy). Результаты — CSV в папке results/.

Что повторено из кода (настройки по умолчанию: мод включён, авто-запас включён, fast sync выключен):
  - замер: в начале каждого тика packetDelay = «сейчас» − время обработки последнего пакета движения,
    среднее по последним 10 тикам (строки 138–166);
  - запас = разброс интервалов прихода пакетов за последние 40 пакетов (выбросы больше 8 мс не считаются),
    зажатый в 6–16 мс (строки 89–123, 238–242);
  - порог пересинхронизации = запас + 4 мс, но не меньше 1,5 кадра (строки 245–257);
  - пересинхронизация не чаще раза в секунду, только при FPS > 40 и если за 10 последних пакетов разброс
    меньше 25 мс (строки 131–134, 207–222);
  - сдвиг = (50 − среднее ожидание) + запас, округлённый вниз до целого числа кадров; растягивается один тик
    (строки 259–295).
Упрощения: сервер не лагает и шлёт пакет движения каждый тик; клиент обрабатывает пакеты в начале кадра,
а тики тоже идут только на границах кадров (так устроен таймер Minecraft); длина кадра гуляет на ±10 %;
часы клиента идут на 20 ppm быстрее или медленнее серверных (оба варианта, результат усреднён);
джиттер — нормальный шум с отклонением sigma на каждый пакет, пакеты приходят по порядку (TCP).
Это модель, а не замер в игре.
"""
import csv
import math
import os

import numpy as np

T = 50            # тик сервера, мс
DELTA = 5         # когда внутри тика сервер отправляет движение, мс
ONE_WAY = 20      # путь пакета до клиента (пинг 40), мс
WARMUP = 10_000   # первые 10 секунд не считаем, мс
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results')
os.makedirs(OUT, exist_ok=True)


def value_range(buf, need):
    """calculateRange: если данных меньше, чем нужно, мод считает разброс равным 12."""
    if len(buf) < need:
        return 12
    return max(buf) - min(buf)


def run(fps, sigma, ppm, mod, minutes=10, seed=1, one_way=ONE_WAY, phase=None):
    rng = np.random.default_rng(seed)
    dur = minutes * 60_000
    frame = 1000.0 / fps
    n = int(dur / T) + 10
    arrive = np.arange(n) * T + DELTA + one_way + sigma * rng.standard_normal(n)
    arrive = np.maximum.accumulate(arrive)                 # TCP отдаёт пакеты по порядку
    rate = 1.0 + ppm * 1e-6                                # часы клиента относительно серверных

    if phase is None:                                      # случайная фаза при запуске
        t, resid = rng.uniform(0, T), rng.uniform(0, 1)
    else:                                                  # фаза задана: равномерно перебираем варианты
        t, resid = 0.0, phase
    ms_per_tick = 50.0
    rate_changed = False
    k_net = k_main = 0
    last_pkt = math.floor(t)
    pending = []
    delay_buf = [12]
    range_buf, fast_buf = [0], [0]
    last_range_time = math.floor(t)
    range_updated = False
    lazy = 0
    avg = 0
    last_sync = math.floor(t)
    offset = 0 if fps > 240 else (1 if fps > 120 else 2)

    def quantize(m):
        if m < frame:
            return int(frame)
        return int(math.floor(m / frame) * frame)

    def margin():
        lo = 8 if lazy > 0 else 6
        return min(max(packet_range, lo), 16)

    waits, stretched, queue = [], [], []
    packet_range = inst_range = 12
    while t < dur:
        now = math.floor(t)
        # поток Netty: пакеты, пришедшие с прошлого кадра (замер разброса — раз за тик)
        while k_net < n and arrive[k_net] <= t:
            a = math.floor(arrive[k_net])
            if not range_updated:
                delta = a - last_range_time
                if delta > 0:
                    dev = ((delta % T) + 25) % T - 25
                    if abs(dev) <= 8:
                        range_buf.append(dev)
                        if len(range_buf) > 40:
                            range_buf.pop(0)
                    fast_buf.append(dev)
                    if len(fast_buf) > 10:
                        fast_buf.pop(0)
                if delta >= 2 * T:
                    lazy = 20
                last_range_time = a
                range_updated = True
            k_net += 1
        # главный поток: в начале кадра обрабатывает всё, что пришло
        while k_main < k_net:
            last_pkt = now
            pending.append(arrive[k_main])
            k_main += 1
        # таймер Minecraft: тики только на границах кадров
        step = frame * (1 + 0.1 * rng.uniform(-1, 1))      # длина кадра по часам клиента
        resid += step / ms_per_tick
        ticks = int(resid)
        resid -= ticks
        for _ in range(min(10, ticks)):
            # onClientTickStart
            pd = now - last_pkt
            delay_buf.append(pd if 0 < pd < 55 else avg)
            if len(delay_buf) > 10:
                delay_buf.pop(0)
            if lazy > 0:
                lazy -= 1
            avg = sum(delay_buf) // len(delay_buf)
            packet_range = value_range(range_buf, 40)
            inst_range = value_range(fast_buf, 10)
            range_updated = False
            # тик применяет всё, что успело прийти
            if t > WARMUP:
                waits.extend(t - a for a in pending)
                # сервер с очередью: удар, отправленный в этот тик, ждёт начала серверного тика
                queue.append((-(t + one_way + sigma * rng.standard_normal())) % T)
            pending.clear()
            # onClientTickEnd
            if rate_changed:
                rate_changed = False
                ms_per_tick = 50.0
            if mod and now - last_sync > 1000 and fps > 40 and inst_range < 25:
                m = margin()
                shift = None
                if len(delay_buf) >= 10 and max(delay_buf) - min(delay_buf) > 35:      # fixWeirdSync
                    last_sync = now
                    shift = quantize(m - min(m // 2, min(delay_buf)))
                    delay_buf, avg = [m], m
                threshold = int(m + 4)
                if threshold < frame:
                    threshold = int(frame * 1.5)
                if threshold < avg:                                                    # matchTickSync
                    last_sync = now
                    shift = (T - avg) + quantize(m + offset)
                    delay_buf, avg = [m], m
                if shift is not None:
                    ms_per_tick = float(max(5, shift + T))
                    rate_changed = True
                    if t > WARMUP:
                        stretched.append(ms_per_tick)
        t += step / rate                                   # переводим кадр в «серверное» время
    w = np.array(waits)
    minutes_counted = (dur - WARMUP) / 60_000
    return w.mean(), len(stretched) / minutes_counted, (np.mean(stretched) if stretched else 0.0), float(np.mean(queue))


if __name__ == '__main__':
    SEEDS = 16   # 16 фаз, равномерно от 0 до 50 мс, и оба направления дрейфа: без мода фаза у каждого запуска своя

    def avg_runs(fps, sigma, mod, one_way=ONE_WAY, seeds=SEEDS):
        res = [run(fps, sigma, 20 if i % 2 else -20, mod=mod, minutes=3, seed=100 + i, one_way=one_way, phase=i / seeds)
               for i in range(seeds)]
        return float(np.mean([r[0] for r in res])), float(np.mean([r[3] for r in res]))

    print('1) Сервер на Paper: сколько данные ждут твоего тика (от прихода пакета до тика), среднее по 16 запускам по 3 минуты')
    print('FPS | джиттер σ | без мода, мс | с модом, мс | выигрыш, мс')
    rows = []
    for fps in (60, 144, 240, 360):
        for sigma in (0.5, 1, 2, 3, 5, 8, 10, 15):
            b, _ = avg_runs(fps, sigma, False)
            m, _ = avg_runs(fps, sigma, True)
            rows.append([fps, sigma, round(b, 1), round(m, 1), round(b - m, 1)])
            print(f'{fps:3} | {sigma:9} | {b:12.1f} | {m:11.1f} | {b - m:11.1f}')
    with open(os.path.join(OUT, 'ticksync_model.csv'), 'w', newline='', encoding='utf-8') as f:
        wr = csv.writer(f)
        wr.writerow(['fps', 'джиттер_мс', 'ожидание_без_мода_мс', 'ожидание_с_модом_мс', 'выигрыш_мс'])
        wr.writerows(rows)

    print('\n2) Пинг: Paper против сервера с очередью (240 FPS, джиттер 1 мс)')
    print('пинг | выигрыш на Paper | очередь: без мода (приём + очередь) | очередь: с модом | выигрыш на очереди')
    rows3 = []
    for ping in range(0, 121, 5):
        rb, qb = avg_runs(240, 1, False, one_way=ping / 2)
        rm, qm = avg_runs(240, 1, True, one_way=ping / 2)
        rows3.append([ping, round(rb - rm, 1), round(rb + qb, 1), round(rm + qm, 1), round((rb + qb) - (rm + qm), 1)])
        print(f'{ping:4} | {rb - rm:16.1f} | {rb + qb:35.1f} | {rm + qm:16.1f} | {(rb + qb) - (rm + qm):18.1f}')
    with open(os.path.join(OUT, 'ticksync_ping.csv'), 'w', newline='', encoding='utf-8') as f:
        wr = csv.writer(f)
        wr.writerow(['пинг_мс', 'выигрыш_Paper_мс', 'очередь_без_мода_мс', 'очередь_с_модом_мс', 'выигрыш_очередь_мс'])
        wr.writerows(rows3)

    print('\n3) Как часто мод пересинхронизируется (30 минут, часы клиента ±20 ppm)')
    print('FPS | джиттер σ | пересинхронизаций в минуту | средняя длина растянутого тика, мс')
    rows2 = []
    for fps in (144, 240):
        for sigma in (1, 2):
            per_min, long_tick = [], []
            for i, ppm in enumerate((20, -20)):
                _, s_, lt, _ = run(fps, sigma, ppm, mod=True, minutes=30, seed=500 + i)
                per_min.append(s_)
                if lt:
                    long_tick.append(lt)
            pm = float(np.mean(per_min))
            lt = float(np.mean(long_tick)) if long_tick else 0.0
            rows2.append([fps, sigma, round(pm, 2), round(lt)])
            print(f'{fps:3} | {sigma:9} | {pm:26.2f} | {lt:34.0f}')
    with open(os.path.join(OUT, 'ticksync_resync.csv'), 'w', newline='', encoding='utf-8') as f:
        wr = csv.writer(f)
        wr.writerow(['fps', 'джиттер_мс', 'пересинхронизаций_в_минуту', 'длина_растянутого_тика_мс'])
        wr.writerows(rows2)
    print('\nCSV сохранены: ticksync_model.csv, ticksync_ping.csv, ticksync_resync.csv')
