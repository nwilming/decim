import numpy as np
from sklearn.metrics import mean_squared_error, r2_score
import pandas as pd
from os.path import join
import nibabel as nib
from sklearn.linear_model import LinearRegression
from nilearn.surface import vol_to_surf
from collections import defaultdict
from patsy import dmatrix
from scipy.interpolate import interp1d


'''
Use script in two steps:

FIRST: Voxel Regressions & Vol2 Surf
    --> per subject & session

SECOND: Concatenate and average magnitude and lateralization
    --> for all
'''


def hrf(t):
    '''
    A hemodynamic response function
    '''
    h = t ** 8.6 * np.exp(-t / 0.547)
    h = np.concatenate((h * 0, h))
    return h / h.sum()


def make_bold(evidence, dt=0.25):
    '''
    Convolve with haemodynamic response function.
    '''
    t = np.arange(0, 20, dt)
    return np.convolve(evidence, hrf(t), 'same')


def interp(x, y, target):
    '''
    Interpolate
    '''
    f = interp1d(x.values.astype(int), y)
    target = target[target.values.astype(int) > min(x.values.astype(int))]
    return pd.DataFrame({y.name: f(target.values.astype(int))}, index=target)


def regular(df, target='16ms'):
    '''
    Set datetime index and resample to target frequency.
    '''
    dt = pd.to_timedelta(df.index.values, unit='ms')
    df = df.set_index(dt)
    target = df.resample(target).mean().index
    return pd.concat([interp(dt, df[c], target) for c in df.columns], axis=1)


#@memory.cache
class VoxelSubject(object):
    def __init__(self, subject, session, runs, flex_dir, BehavDataframe, task):
        self.subject = subject
        self.session = session
        self.runs = runs
        self.flex_dir = flex_dir
        self.BehavDataframe = BehavDataframe
        self.voxel_regressions = {}
        self.surface_textures = defaultdict(dict)
        self.task = task

    def design_matrix(self, behav):
        '''
        Concatenate runwise BOLD- and behavioral timeseries per subject-session.
        Regress each voxel on each behavioral parameter.

        Return one Nifti per session, subject & parameter with four frames:
            coef_, intercept_, r2_score, mean_squared_error

        Z-score voxel (not behavior anymore...)
        '''
        print('load glm data...')
        # Split into categorical and numerical regressors
        continuous = behav.loc[:, ['belief', 'LLR', 'surprise', 'onset']]
        categorical = behav.loc[:, ['response', 'stimulus', 'switch', 'rule_resp', 'event']]
        categorical.loc[categorical.stimulus.isin([-1, 1]), 'rule_resp'] =\
            categorical.iloc[categorical.loc[categorical.stimulus.isin([-1, 1])].index + 1].rule_resp.values  # rule_resp at onset of stimulus
        categorical.stimulus = categorical.stimulus.fillna(method='ffill', limit=2)  # stimulus lasts until offset
        categorical = categorical.fillna(0)
        combined = pd.concat([categorical, continuous], axis=1)
        combined = combined.set_index((combined.onset.values * 1000).astype(int)).drop('onset', axis=1)
        combined = combined.reindex(pd.Index(np.arange(0, combined.index[-1] + 15000, 1)))
        combined = combined.fillna(method='ffill', limit=99)
        combined = combined.loc[np.arange(combined.index[0], combined.index[-1], 100)]
        combined.loc[0] = 0
        combined.loc[:, ['stimulus', 'response', 'switch', 'rule_resp', 'surprise', 'LLR']] =\
            combined.loc[:, ['stimulus', 'response', 'switch', 'rule_resp', 'surprise', 'LLR']].fillna(0)
        combined.belief = combined.belief.fillna(method='ffill')

        combined.stimulus = combined.stimulus.map({-1: 'horizontal', 1: 'vertical', 0: 'none'})
        combined.response = combined.response.map({-1: 'left', 1: 'right', 0: 'none'})
        combined.rule_resp = combined.rule_resp.map({-1: 'A', 1: 'B', 0: 'none'})
        # build design matrix using patsy formulas
        s = ['none', 'vertical', 'horizontal']
        b = ['none', 'left', 'right']
        r = ['none', 'A', 'B']
        if self.task == 'instructed':
            design_matrix = dmatrix('''switch + np.abs(switch) +
                            C(stimulus, levels=s) + C(response, levels=b) + C(rule_resp, levels=r) +
                            (C(stimulus, levels=s) + C(response, levels=b)):C(rule_resp, levels=r)''', data=combined)
        elif self.task == 'inference':
            design_matrix = dmatrix('''belief + np.abs(belief) + switch + np.abs(switch) + LLR + np.abs(LLR)+ surprise +
                C(stimulus, levels=s) + C(response, levels=b) + C(rule_resp, levels=r) +
                (C(stimulus, levels=s) + C(response, levels=b)):C(rule_resp, levels=r)''', data=combined)

        dm = pd.DataFrame(design_matrix, columns=design_matrix.design_info.column_names, index=combined.index)

        for column in dm.columns:
            print('Align ', column)
            dm[column] = make_bold(dm[column].values, dt=.1)
        dm = regular(dm, target='1900ms')
        dm.loc[pd.Timedelta(0)] = 0
        dm = dm.sort_index()
        return dm.drop('Intercept', axis=1)

    def concat_runs(self, denoise=False):
        session_nifti = []
        session_behav = []
        for run in self.runs:
            behav = self.design_matrix(self.BehavDataframe[run])
            if denoise is True:
                nifti = nib.load(join(self.flex_dir, 'fmri', 'completed_preprocessed', self.subject, 'fmriprep', self.subject, self.session, 'func',
                                      '{0}_{1}_task-{2}_bold_space-T1w_preproc_denoise.nii.gz'.format(self.subject, self.session, run)))
            else:
                nifti = nib.load(join(self.flex_dir, 'fmri', 'completed_preprocessed', self.subject, 'fmriprep', self.subject, self.session, 'func',
                                      '{0}_{1}_task-{2}_bold_space-T1w_preproc.nii.gz'.format(self.subject, self.session, run)))

            self.nifti_shape = nifti.get_data().shape
            self.nifti_affine = nifti.affine
            data = nifti.get_data()
            d2 = np.stack([data[:, :, :, i].ravel() for i in range(data.shape[-1])])
            if len(d2) > len(behav):
                d2 = d2[0: len(behav)]
            elif len(d2) < len(behav):
                behav = behav.iloc[0:len(d2)]
            session_behav.append(behav)
            session_nifti.append(pd.DataFrame(d2))
        session_nifti = pd.concat(session_nifti, ignore_index=True)
        session_behav = pd.concat(session_behav, ignore_index=True)
        assert session_behav.shape[0] == session_nifti.shape[0]
        self.session_nifti = session_nifti
        self.session_behav = session_behav

    def glm(self):
        voxels = self.session_nifti
        behav = self.session_behav
        # z-scoring
        voxels = (voxels - voxels.mean()) / voxels.std()
        voxels = voxels.fillna(0)  # because if voxels have std == 0 --> NaNs introduced
        behav = (behav - behav.mean()) / behav.std()
        self.DesignMatrix = behav
        linreg = LinearRegression()
        print('fit', self.task)
        linreg.fit(behav.values, voxels.values)
        predict = linreg.predict(behav.values)
        for i, parameter in enumerate(behav.columns):
            reg_result = np.concatenate(([linreg.coef_[:, i].flatten()], [linreg.intercept_],
                                         [r2_score(voxels, predict, multioutput='raw_values')],
                                         [mean_squared_error(voxels, predict, multioutput='raw_values')]), axis=0)
            new_shape = np.stack([reg_result[i, :].reshape(self.nifti_shape[0:3]) for i in range(reg_result.shape[0])], -1)
            new_image = nib.Nifti1Image(new_shape, affine=self.nifti_affine)
            self.voxel_regressions[parameter] = new_image

    def vol_2surf(self, radius=.3):
        for param, img in self.voxel_regressions.items():
            for hemisphere in ['L', 'R']:
                pial = join(self.flex_dir, 'fmri', 'completed_preprocessed',
                            self.subject,
                            'fmriprep', self.subject, 'anat', '{0}_T1w_pial.{1}.surf.gii'.format(self.subject, hemisphere))
                surface = vol_to_surf(img, pial, radius=radius, kind='line')
                self.surface_textures[param][hemisphere] = pd.DataFrame(surface, columns=['coef_', 'intercept_', 'r2_score', 'mean_squared_error'])


#@memory.cache
def execute(subject, session, runs, flex_dir, BehavDataframe, task):
    v = VoxelSubject(subject, session, runs, flex_dir, BehavDataframe, task)
    v.concat_runs(denoise=False)
    v.glm()
    v.vol_2surf()
    return v.voxel_regressions, v.surface_textures, v.DesignMatrix


'''
runs = ['instructed_run-7', 'instructed_run-8']
behav = {run: pd.read_hdf('/Volumes/flxrl/FLEXRULE/GLM/Sublevel_GLM_Climag_2018-12-07-a/sub-17/BehavFrame_sub-17_ses-2.hdf', key=run) for run in runs}
execute('sub-3', 'ses-2', runs, '/Volumes/flxrl/FLEXRULE', behav, 'inference')
'''
