#!/usr/bin/env python3
"""
Симуляция к видео «Скрытый пинг Майнкрафта, которого нет в табе».

Что считает (запуск: python models/simulation.py, нужен только numpy):
  1. Сколько данные сервера ждут клиентского тика при случайной фазе (0–50 мс, в среднем 25).
  2. Сколько выигрывает выравнивание фазы (мод вроде Tick Sync) при разном джиттере сети.
  3. Как выигрыш зависит от пинга: на Paper (сервер обрабатывает пакеты сразу)
     и на сервере с очередью (ваниль 1.21.9+, 1.8: пакеты ждут начала серверного тика).
  4. Кто первым попадает в размене при сближении: проверка правила «пинг + ожидание тика».

Допущения (упрощённая модель, а не замер в игре):
  - тик = 50 мс у сервера и у клиента; сервер рассылает данные через DELTA мс после начала тика;
  - пинг симметричный: в каждую сторону половина пинга;
  - джиттер — нормальное распределение с отклонением sigma на каждый путь;
  - мод ставит тик через «запас» мс после прихода пакета; запас подбирается лучший для данного джиттера;
  - в размене оба игрока бегут навстречу с одинаковой скоростью и кликают, когда соперник
    на их экране входит в одну и ту же дистанцию; клик ждёт ближайшего тика (0–50 мс, случайно).
Результаты пишутся в CSV в папку results/.
"""
import csv
import os

import numpy as np

T = 50.0          # длина тика, мс
DELTA = 5.0       # сколько сервер тратит на тик до рассылки данных, мс
N = 200_000       # число случайных испытаний
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results')
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(20261010)


def write_csv(name, header, rows):
    with open(os.path.join(OUT, name), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# 1. Случайная фаза: ожидание до тика
waits = rng.uniform(0, T, N)
print('1) Случайная фаза: ожидание тика')
print(f'   среднее {waits.mean():.1f} мс, минимум {waits.min():.1f}, максимум {waits.max():.1f}')
hist, edges = np.histogram(waits, bins=10, range=(0, T))
write_csv('random_phase_wait_histogram.csv', ['от_мс', 'до_мс', 'доля'],
          [[int(a), int(b), round(h / N, 4)] for a, b, h in zip(edges[:-1], edges[1:], hist)])


# 2. Выигрыш от выравнивания при разном джиттере (Paper: важна только сторона приёма)
def receive_wait(margin, sigma, jitter):
    """Мод ставит тик через `margin` мс после ожидаемого прихода; джиттер сдвигает приход."""
    return np.mod(margin - sigma * jitter, T)


jit = rng.normal(0, 1, N)
print('\n2) Выигрыш выравнивания в зависимости от джиттера (сервер на Paper)')
print('   джиттер σ | лучший запас | осталось ожидания | выигрыш | опоздавших пакетов')
rows2 = []
best_margin = {}
for sigma in (0, 1, 2, 3, 5, 8, 10, 15):
    cands = np.arange(0.5, 30.01, 0.5)
    costs = [receive_wait(m, sigma, jit).mean() for m in cands]
    m = float(cands[int(np.argmin(costs))]) if sigma > 0 else 0.5
    w = receive_wait(m, sigma, jit)
    late = float((sigma * jit > m).mean())
    best_margin[sigma] = m
    gain = 25 - w.mean()
    rows2.append([sigma, m, round(w.mean(), 1), round(gain, 1), round(late, 3)])
    print(f'   {sigma:9} | {m:12.1f} | {w.mean():17.1f} | {gain:7.1f} | {late:18.3f}')
write_csv('gain_vs_jitter.csv', ['джиттер_мс', 'запас_мс', 'ожидание_мс', 'выигрыш_мс', 'доля_опоздавших'], rows2)


# 3. Выигрыш в зависимости от пинга: Paper против сервера с очередью
def queued_total(phi, ping, s_dn, s_up, jd, ju):
    """Ожидание на приёме + ожидание серверного тика для своего пакета (сервер с очередью)."""
    arr = DELTA + ping / 2 + s_dn * jd                 # данные пришли к клиенту
    w_recv = np.mod(phi - arr, T)                      # ждут клиентского тика (фаза phi)
    arr_srv = phi + ping / 2 + s_up * ju               # пакет клиента пришёл на сервер
    w_srv = np.mod(-arr_srv, T)                        # ждёт начала серверного тика
    return (w_recv + w_srv).mean()


print('\n3) Выигрыш в зависимости от пинга (джиттер 2 мс)')
print('   пинг | Paper | очередь: случайная фаза | очередь: выравнивание как у мода | выигрыш на очереди')
jd, ju = rng.normal(0, 1, N), rng.normal(0, 1, N)
sigma = 2.0
m = best_margin[2]
paper_gain = 25 - receive_wait(m, sigma, jit).mean()
rows3 = []
for ping in range(0, 121, 5):
    phi_mod = DELTA + ping / 2 + m                    # мод ставит тик сразу после прихода + запас
    q_mod = queued_total(phi_mod, ping, sigma, sigma, jd, ju)
    q_gain = T - q_mod                                # при случайной фазе в среднем ровно 50
    rows3.append([ping, round(paper_gain, 1), 50.0, round(q_mod, 1), round(q_gain, 1)])
    print(f'   {ping:4} | {paper_gain:5.1f} | {50.0:23.1f} | {q_mod:32.1f} | {q_gain:18.1f}')
write_csv('gain_vs_ping.csv', ['пинг_мс', 'выигрыш_Paper_мс', 'очередь_случайно_мс', 'очередь_с_модом_мс', 'выигрыш_очередь_мс'], rows3)


# 4. Размен при сближении: кто первым долетает до сервера (сервер на Paper)
def trade(ping_a, wait_a, ping_b, wait_b, n=N):
    """
    Каждый видит соперника с опозданием: его путь до сервера + свой путь от сервера + своё ожидание тика.
    Кликает, когда соперник на экране входит в одну и ту же дистанцию. Сближение 2v, значит
    момент клика сдвигается на половину опоздания картинки. Клик ждёт своего тика (0–50 мс),
    потом пакет летит на сервер половину пинга.
    """
    age_a = ping_b / 2 + ping_a / 2 + wait_a
    age_b = ping_a / 2 + ping_b / 2 + wait_b
    click_a = age_a / 2 + rng.uniform(0, T, n)
    click_b = age_b / 2 + rng.uniform(0, T, n)
    hit_a = click_a + ping_a / 2
    hit_b = click_b + ping_b / 2
    return float((hit_b < hit_a).mean()), float((hit_a - hit_b).mean())


print('\n4) Размен при сближении: доля разменов, где Б попадает первым')
rows4 = []
for pa, wa, pb, wb in ((40, 43, 40, 5), (40, 25, 40, 25), (30, 45, 60, 5), (20, 45, 20, 5), (2, 43, 2, 5), (2, 43, 40, 5), (2, 45, 20, 5)):
    p, d = trade(pa, wa, pb, wb)
    rows4.append([pa, wa, pb, wb, pa + wa, pb + wb, round(p, 3), round(d, 1)])
    print(f'   А: пинг {pa} + ожидание {wa} = {pa + wa:3} | Б: пинг {pb} + ожидание {wb} = {pb + wb:3}'
          f' | Б первым в {p * 100:.0f}% разменов, в среднем раньше на {d:.1f} мс')
write_csv('trade_first_hit.csv', ['пинг_А', 'ожидание_А', 'пинг_Б', 'ожидание_Б', 'сумма_А', 'сумма_Б', 'доля_Б_первым', 'разница_мс'], rows4)

print('\nCSV-файлы сохранены в results/.')
