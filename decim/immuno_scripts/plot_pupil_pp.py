from glob import glob
from os.path import join
import pandas as pd
import numpy as np
from matplotlib import pyplot as plt
import seaborn as sns
from itertools import product

subjects = {'VPIM01': 1, 'VPIM02': 2, 'VPIM03': 3, 'VPIM04': 4, 'VPIM06': 6, 'VPIM07': 7, 'VPIM09': 9}
sessions = {'A': 1, 'B': 2, 'C': 3}
blocks = [1, 2, 3, 4, 5, 6, 7]

# INPUT FILES: 'session-pupilframes'
pa = '/Users/kenohagena/Documents/immuno/da/decim/pupilframes/session_pupilframes_230218/'

# TRANSFORM INPUT
frames = {}
for subject, session in product(subjects, sessions):
    file = glob(join(pa, '*{0}{1}.csv'.format(subjects[subject], sessions[session])))
    df = pd.read_csv(file[0])
    frames['{0}{1}'.format(subject, session)] = df.loc[:, ['blink', 'all_artifacts', 'block', 'biz']]

# PLOT
ys = np.linspace(1, 9, 7)

for session in sessions:
    f, ax = plt.subplots(7, 1, figsize=(20, 50))
    for b in range(7):
        blo = blocks[b]
        for position, subject in zip(ys, subjects):
            if (subject == 'VPIM03') & (session == 'B') & (blo == 7):
                continue
            else:
                df = frames['{0}{1}'.format(subject, session)]
                df = df.loc[df.block == blo]
                pupil = df.loc[:, 'biz'].values
                ax[b].plot(pupil * .2 + position, color='black', alpha=.5)

                artifacts = df.loc[df.all_artifacts == True].index - df.iloc[0].name
                blinks = df.loc[df.blink == True].index - df.iloc[0].name
                ax[b].scatter(artifacts, np.repeat(position, len(artifacts)), color='y', marker='|', s=1000, alpha=.3)
                ax[b].scatter(blinks, np.repeat(position, len(blinks)), color='r', marker='|', s=500, alpha=.3)

        ax[b].set_ylim((0, 10))
        ax[b].set(yticks=ys, yticklabels=subjects, title='Session: {0}, Block: {1}'.format(session, blo))
        ax[b].tick_params(
            axis='y',
            which='both',
            left='off',
            right='off',
            labelsize=16)
        ax[b].spines['top'].set_visible(False)
        ax[b].spines['right'].set_visible(False)
        ax[b].spines['left'].set_visible(False)
        #f.subplots_adjust(left=None, right=None, bottom=None, top=None)
        ax[b].set_xlim((0, 600000))
    f.savefig('pp_pupil_session{}.png'.format(session), dpi=160)
