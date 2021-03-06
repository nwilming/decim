from glob import glob
from os.path import join
import pandas as pd
import numpy as np
from matplotlib import pyplot as plt
import seaborn as sns


# INPUT
df = pd.read_csv('/Users/kenohagena/Documents/immuno/da/decim/g_pupilframes/cpf12_all.csv', header=[0, 1, 2], index_col=[0, 1, 2, 3], dtype=np.float64)

# TRANSFORM INPUT
clean = df.loc[(df.pupil.parameter.blink == 0) & (df.pupil.parameter.all_artifacts < .2)]
rt = clean.behavior.parameter.reaction_time
t = clean.pupil.triallock
t = t.set_index(rt)
t = t.sort_index(ascending=False).dropna()

# PLOTf,
f, ax = plt.subplots(figsize=(10, 10))
ax.imshow(t, aspect='auto')
ax.set_yticks([0, len(t)])
ax.set_yticklabels(['high RT', 'low RT'])
ax.set_xticks(np.arange(0, 12000, 1000))
ax.set_xticklabels([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
ax.set(title='Grating onset locked trials sorted by reaction time', xlabel='Time (s)', ylabel='Trial')
ax.axvline(1000, color='0.1')
f.savefig('gratinglock_imshow.png', dpi=160)
