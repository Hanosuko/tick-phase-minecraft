#!/usr/bin/env python3
"""
Разбор нашего теста: Hanosuko и PynPun, оба из Москвы, одинаковый пинг, мод Tick Sync то у одного, то у другого.
Запуск: python test/test_analysis.py (нужен scipy). Данные — test_raundy.csv рядом со скриптом.

Порядок сессий — «туда-обратно» (мод у Hanosuko, у PynPun, у PynPun, у Hanosuko), это снимает часть
эффекта разминки и усталости. Но игроки знали, у кого мод, раундов мало, а раунды не независимы
(тильт, разгон). Поэтому это иллюстрация, а не доказательство.
"""
import csv
import os

from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(os.path.join(HERE, 'test_raundy.csv'), encoding='utf-8')))


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return c - h, c + h


print('1) По сессиям: сколько раундов выиграл тот, у кого мод')
sessions = sorted({r['сессия'] for r in rows}, key=int)
for s in sessions:
    rr = [r for r in rows if r['сессия'] == s]
    mod = rr[0]['с_модом']
    won = sum(r['победил'] == mod for r in rr)
    print(f'   сессия {s}: {rr[0]["сервер"]}, пинг {rr[0]["пинг"]}, мод у {mod}: {won} из {len(rr)}')

print('\n2) По игрокам: доля выигранных раундов с модом и без')
table = {}
for p in ('Hanosuko', 'PynPun'):
    for has in (True, False):
        rr = [r for r in rows if (r['с_модом'] == p) == has]
        k = sum(r['победил'] == p for r in rr)
        lo, hi = wilson(k, len(rr))
        table[(p, has)] = (k, len(rr))
        print(f'   {p:8} {"с модом " if has else "без мода"}: {k:2} из {len(rr):2} = {k / len(rr):4.0%}'
              f'  (95% интервал {lo:.0%}–{hi:.0%})')

# Точный тест Фишера: выигрыши Hanosuko, когда мод у него, против раундов, когда мод у PynPun.
# Условие на итоговые суммы убирает разницу в силе игроков из сравнения.
(k1, n1), (k2, n2) = table[('Hanosuko', True)], table[('Hanosuko', False)]
ct = [[k1, n1 - k1], [k2, n2 - k2]]
odds, p_one = stats.fisher_exact(ct, alternative='greater')
_, p_two = stats.fisher_exact(ct, alternative='two-sided')
ci = stats.contingency.odds_ratio(ct).confidence_interval(0.95)
print('\n3) Точный тест Фишера (мод у Hanosuko против мода у PynPun, считаем раунды Hanosuko)')
print(f'   таблица {ct}; отношение шансов {odds:.1f} (95% интервал {ci.low:.1f}–{ci.high:.0f})')
print(f'   p (односторонний) = {p_one:.3f}; p (двусторонний) = {p_two:.3f}')

mod_wins = sum(r['победил'] == r['с_модом'] for r in rows)
bt = stats.binomtest(mod_wins, len(rows), 0.5, alternative='greater')
print(f'\n4) Без учёта силы игроков: тот, у кого мод, выиграл {mod_wins} из {len(rows)} = {mod_wins / len(rows):.0%};'
      f' биномиальный тест p = {bt.pvalue:.2f}')

rr = [r for r in rows if r['сессия'] == '4']
first, last = rr[:8], rr[8:]
a = sum(r['победил'] == 'Hanosuko' for r in first)
b = sum(r['победил'] == 'Hanosuko' for r in last)
_, p4 = stats.fisher_exact([[b, len(last) - b], [a, len(first) - a]], alternative='greater')
print(f'\n5) Сессия 4: пока у PynPun был природный «Поток» (раунды 1–8), Hanosuko с модом выиграл {a} из {len(first)};'
      f' после (раунды 9–13) — {b} из {len(last)}. p = {p4:.2f}, и границу мы выбрали уже после игры, так что это лишь наблюдение.')

RES = os.path.join(os.path.dirname(HERE), 'results'); os.makedirs(RES, exist_ok=True)
with open(os.path.join(RES, 'test_summary.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['игрок', 'мод', 'выиграл', 'раундов', 'доля'])
    for (p, has), (k, n) in table.items():
        w.writerow([p, 'да' if has else 'нет', k, n, round(k / n, 3)])
print('\nСводка сохранена: results/test_summary.csv')
