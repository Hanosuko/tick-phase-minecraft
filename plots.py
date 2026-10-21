#!/usr/bin/env python3
"""
Графики для README из CSV в results/. Запуск: python plots.py (нужен matplotlib).
Каждый график сохраняется в двух вариантах: светлый (name.png) и тёмный (name_dark.png) —
GitHub сам покажет нужный под тему.
"""
import csv
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(ROOT, 'results')
OUT = os.path.join(RES, 'charts')
os.makedirs(OUT, exist_ok=True)

THEMES = {
    'light': dict(surface='#fcfcfb', text='#0b0b0b', text2='#52514e', grid='#e4e3df',
                  series=['#2a78d6', '#eb6834', '#1baf7a', '#eda100'], neutral='#a8a69f'),
    'dark': dict(surface='#1a1a19', text='#f0efec', text2='#c3c2b7', grid='#33332f',
                 series=['#3987e5', '#d95926', '#199e70', '#c98500'], neutral='#6e6c66'),
}


def read(name):
    with open(os.path.join(RES, name), encoding='utf-8') as f:
        return list(csv.DictReader(f))


def setup(th, title, subtitle):
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=160)
    fig.patch.set_facecolor(th['surface']); ax.set_facecolor(th['surface'])
    for s in ('top', 'right', 'left'):
        ax.spines[s].set_visible(False)
    ax.spines['bottom'].set_color(th['grid'])
    ax.tick_params(colors=th['text2'], labelsize=9, length=0)
    ax.grid(axis='y', color=th['grid'], linewidth=0.8); ax.set_axisbelow(True)
    fig.text(0.07, 0.95, title, fontsize=13, fontweight='bold', color=th['text'], va='top')
    fig.text(0.07, 0.885, subtitle, fontsize=9.5, color=th['text2'], va='top')
    fig.subplots_adjust(left=0.07, right=0.86, top=0.80, bottom=0.13)
    return fig, ax


def save(fig, name, mode):
    fig.savefig(os.path.join(OUT, f'{name}{"" if mode == "light" else "_dark"}.png'), facecolor=fig.get_facecolor())
    plt.close(fig)


for mode, th in THEMES.items():
    # 1. Выигрыш Tick Sync от джиттера при разном FPS (модель по исходникам)
    rows = read('ticksync_model.csv')
    fig, ax = setup(th, 'Сколько даёт Tick Sync: чем ровнее сеть и выше FPS, тем больше',
                    'Среднее сокращение ожидания тика, мс. Модель алгоритма мода по исходникам, сервер на Paper')
    for i, fps in enumerate(('60', '144', '240')):       # 360 FPS почти совпадает с 240 — он есть в CSV
        r = [x for x in rows if x['fps'] == fps]
        xs = [float(x['джиттер_мс']) for x in r]; ys = [float(x['выигрыш_мс']) for x in r]
        ax.plot(xs, ys, color=th['series'][i], linewidth=2, marker='o', markersize=5,
                markeredgecolor=th['surface'], markeredgewidth=1.2, label=f'{fps} FPS')
        y3 = ys[xs.index(3.0)]
        ax.text(3.25, y3 + {'60': -1.3, '144': -1.4, '240': 1.2}[fps], f'{fps} FPS', color=th['text2'], fontsize=9, va='center')
    ax.axhline(25, color=th['neutral'], linewidth=1, linestyle=(0, (4, 3)))
    ax.text(0.3, 25.6, 'обещание из рекламы — 25 мс (теоретический потолок)', color=th['text2'], fontsize=8.5)
    ax.set_xlabel('джиттер сети (разброс пинга), мс', color=th['text2'], fontsize=9.5)
    ax.set_ylim(0, 27); ax.set_xlim(0, 16.5)
    ax.legend(frameon=False, labelcolor=th['text2'], fontsize=9, loc='upper right', bbox_to_anchor=(1.17, 0.95))
    save(fig, 'ticksync_gain_vs_jitter', mode)

    # 2. Выигрыш от пинга: Paper против сервера с очередью
    rows = read('ticksync_ping.csv')
    fig, ax = setup(th, 'На Paper выигрыш не зависит от пинга, на сервере с очередью — пила',
                    'Сокращение задержки, мс, при 240 FPS и джиттере 1 мс. Модель Tick Sync')
    xs = [float(x['пинг_мс']) for x in rows]
    for i, (col, lab) in enumerate((('выигрыш_Paper_мс', 'Paper и форки'), ('выигрыш_очередь_мс', 'сервер с очередью (ваниль 1.21.9+, 1.8)'))):
        ys = [float(x[col]) for x in rows]
        ax.plot(xs, ys, color=th['series'][i], linewidth=2, marker='o', markersize=4.5,
                markeredgecolor=th['surface'], markeredgewidth=1, label=lab)
    ax.set_xlabel('пинг, мс', color=th['text2'], fontsize=9.5); ax.set_ylim(-2, 40)
    ax.legend(frameon=False, labelcolor=th['text2'], fontsize=9, loc='lower left', bbox_to_anchor=(0, 0.99), ncol=2)
    save(fig, 'gain_vs_ping', mode)

    # 3. Лотерея фазы: сколько данные ждут тика при случайной фазе
    rows = read('random_phase_wait_histogram.csv')
    fig, ax = setup(th, 'Случайная фаза: любое ожидание от 0 до 50 мс одинаково вероятно',
                    'Доля запусков игры по времени ожидания тика, 200 000 испытаний. В среднем — 25 мс')
    lefts = [float(x['от_мс']) for x in rows]; vals = [float(x['доля']) * 100 for x in rows]
    ax.bar([l + 2.5 for l in lefts], vals, width=4.6, color=th['series'][0], edgecolor=th['surface'], linewidth=2)
    ax.axvline(25, color=th['neutral'], linewidth=1, linestyle=(0, (4, 3)))
    ax.text(25.6, 11.3, 'среднее 25 мс', color=th['text2'], fontsize=9)
    ax.set_xlabel('ожидание до тика клиента, мс', color=th['text2'], fontsize=9.5)
    ax.set_ylabel('% запусков', color=th['text2'], fontsize=9.5); ax.set_ylim(0, 12.5); ax.set_xlim(0, 50)
    save(fig, 'random_phase_wait', mode)

    # 4. Наш тест: доля выигранных раундов с модом и без
    rows = read('test_summary.csv')
    fig, ax = setup(th, 'Наш тест, 32 раунда: с модом каждый выигрывал чаще',
                    'Доля выигранных раундов. Без слепого метода и раундов мало — это иллюстрация, а не доказательство')
    players = ['PynPun', 'Hanosuko']
    for j, (has, lab, col) in enumerate((('нет', 'без мода', th['neutral']), ('да', 'с модом', th['series'][0]))):
        for i, p in enumerate(players):
            r = [x for x in rows if x['игрок'] == p and x['мод'] == has][0]
            v = float(r['доля']) * 100
            ax.bar(i + (j - 0.5) * 0.36, v, width=0.34, color=col, edgecolor=th['surface'], linewidth=2,
                   label=lab if i == 0 else None)
            ax.text(i + (j - 0.5) * 0.36, v + 2, f'{r["выиграл"]} из {r["раундов"]}', ha='center', color=th['text'], fontsize=9)
    ax.set_xticks(range(len(players))); ax.set_xticklabels(players, fontsize=10, color=th['text'])
    ax.set_ylabel('% выигранных раундов', color=th['text2'], fontsize=9.5); ax.set_ylim(0, 105)
    ax.legend(frameon=False, labelcolor=th['text2'], fontsize=9, loc='upper right', bbox_to_anchor=(1.17, 0.95))
    save(fig, 'test_win_share', mode)

print('Графики сохранены в results/charts/')
