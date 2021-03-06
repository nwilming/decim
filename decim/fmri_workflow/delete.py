from decim import roi_extract as re
import pandas as pd
import numpy as np
from os.path import join, expanduser
from glob import glob
from decim import slurm_submit as slu
import sys
from nilearn import surface
import nibabel as ni


epi_dir = '/home/khagena/FLEXRULE/fmri/completed_preprocessed'
atlas_dir = '/home/khagena/FLEXRULE/fmri/atlases'
out_dir = '/home/khagena/FLEXRULE/fmri/roi_extract'
subjects = [12, 13, 14, 19, 20, 21]
sessions = ['ses-2', 'ses-3']
runs = ['inference_run-4',
        'inference_run-5',
        'inference_run-6',
        'instructed_run-7',
        'instructed_run-8']
atlases = {
    'AAN_DR': 'aan_dr',
    'basal_forebrain_4': 'zaborsky_bf4',
    'basal_forebrain_123': 'zaborsky_bf123',
    'LC_Keren_2std': 'keren_lc_2std',
    'LC_standard': 'keren_lc_1std',
    'NAc': 'nac',
    'SNc': 'snc',
    'VTA': 'vta'
}
cit168 = ['nac', 'snc', 'vta']  # These have a different shape ((X, 1) vs. (1, X))
h = {'lh': 'L',
     'rh': 'R'}


def extract_brainstem_roi(sub, epi_dir, atlas_dir, out_dir):
    '''
    Load EPIs and masks and resmaple the Epis to the masks.
    Output: Masked EPIs and weight file per atlas
    '''
    instruct = 'instructed*T1w*prepro*denoise'
    infer = 'infer*T1w*prepro*denoise'
    slu.mkdir_p(out_dir)
    e = re.EPI(sub, out_dir=out_dir)
    e.load_epi('{1}/sub-{0}/fmriprep/sub-{0}/ses-3/func/'.format(sub, epi_dir),
               identifier=infer)
    e.load_epi('{1}/sub-{0}/fmriprep/sub-{0}/ses-2/func/'.format(sub, epi_dir),
               identifier=infer)
    '''
    e.load_epi('{1}/sub-{0}/fmriprep/sub-{0}/ses-2/func/'.format(sub, epi_dir),
               identifier=instruct)
    e.load_epi('{1}/sub-{0}/fmriprep/sub-{0}/ses-3/func/'.format(sub, epi_dir),
               identifier=instruct)
    '''
    print('{} loaded'.format(sub))
    e.load_mask(expanduser('{1}/sub-{0}'.format(sub, atlas_dir)), mult_roi_atlases={'CIT': {2: 'NAc', 6: 'SNc', 10: 'VTA'}})
    e.resample_masks()
    print('{} resampled'.format(sub))
    e.mask()
    print('{} masked'.format(sub))
    e.save()


def concat_single_rois(sub, out_dir):
    '''
    Take outputs of extract_brainstem_roi and concat to a neat pandas MltiIndex DF per subject
    '''
    subject = 'sub-{}'.format(sub)
    home = '{1}/{0}/'.format(subject, out_dir)
    roi_dfs = []
    for session in sessions:
        for run in runs:
            runwise = []
            for atlas, name in atlases.items():
                file = sorted(glob(join(home, '*{0}*{1}*{2}*'.format(session, run, atlas))))
                if len(file) == 0:
                    pass
                else:
                    df = pd.read_csv(file[0], index_col=0)
                    cols = pd.MultiIndex.from_product([[name], range(df.shape[1])], names=['roi', 'voxel'])
                    design = pd.DataFrame(np.full(df.shape, np.nan), columns=cols)
                    design[name] = df.values
                    runwise.append(design)
            if len(file) == 0:
                pass
            else:
                concat = pd.concat(runwise, axis=1, ignore_index=False)
                concat['session'] = session
                concat['run'] = run
                roi_dfs.append(concat)

    df = pd.concat(roi_dfs, axis=0)
    df.index.name = 'frame'
    df = df.set_index(['session', 'run', df.index])
    df.to_csv(join(home, '{}_rois_indexed.csv'.format(subject)), index=True)


def extract_cortical_roi(sub, session, run, epi_dir, combined=True):
    '''
    INPUT: surface annotaions & functional file per run in subject space (fsnative)
    --> Z-score per vertex and average across vertices per annotation label.
    OUTPUT: DF w/ labels as columns & timpoints as rows
    '''
    hemispheres = []
    for hemisphere, hemi in h.items():
        subject = 'sub-{}'.format(sub)
        if combined is True:
            annot_path = join(epi_dir, subject, 'freesurfer', subject, 'label', '{0}.HCPMMP1_combined.annot'.format(hemisphere))
        else:
            annot_path = join(epi_dir, subject, 'freesurfer', subject, 'label', '{0}.HCPMMP1.annot'.format(hemisphere))
        lh_func_path = glob(join(epi_dir, subject, 'fmriprep', subject, session, 'func', '*{0}*fsnative.{1}.func.gii'.format(run, hemi)))[0]
        annot = ni.freesurfer.io.read_annot(annot_path)
        if combined is True:
            labels = [
                '23_inside',
                '19_cingulate_anterior_prefrontal_medial',
                '11_auditory_association',
                '03_visual_dors',
                '22_prefrontal_dorsolateral',
                '10_auditory_primary',
                '02_visual_early',
                '21_frontal_inferior',
                '17_parietal_inferior',
                '12_insular_frontal_opercular',
                '14_lateral_temporal',
                '05_visual_lateral',
                '13_temporal_medial',
                '20_frontal_orbital_polar',
                '07_paracentral_lob_mid_cingulate',
                '18_cingulate_posterior',
                '09_opercular_posterior',
                '08_premotor',
                '01_visual_primary',
                '06_somatosensory_motor',
                '16_parietal_superior',
                '15_temporal_parietal_occipital_junction',
                '04_visual_ventral'
            ]
            labels = [i + '_{}'.format(hemisphere) for i in labels]
        else:
            labels = annot[2]
            labels = [i.astype('str') for i in labels]
        affiliation = annot[0]
        surf = surface.load_surf_data(lh_func_path)
        surf_df = pd.DataFrame(surf).T
        # z-score per vertex
        surf_df = (surf_df - surf_df.mean()) / surf_df.std()
        surf_df = surf_df.T
        surf_df['label_index'] = affiliation
        df = surf_df.groupby('label_index').mean().T
        df.columns = labels
        hemispheres.append(df)
    return pd.concat(hemispheres, axis=1)


def weighted_average(sub, session, run, atlas, roi_dir):
    '''
    INPUT: Roi extracts & weight file (outputs of extract_brainstem_roi)
    --> Normalize weights (sum == 0)
    --> Z-score per voxel
    --> roi * weights
    OUTPUT: 1-D weighted timeseries of ROI
    '''
    subject = 'sub-{}'.format(sub)
    roi = pd.read_csv(glob(join(roi_dir, subject, '{0}*{1}*{2}*{3}*'.format(subject, session, run, atlas)))[0], index_col=0)
    weight = pd.read_csv(glob(join(roi_dir, subject, '{0}_{1}*resampled_weights'.format(subject, atlas)))[0], index_col=0)
    if atlases[atlas] not in cit168:
        weight = weight.T
    # z-score per voxel
    roi = (roi - roi.mean()) / roi.std()

    # normalize weights ...
    weight = weight / weight.sum()

    weighted = np.dot(roi, weight)
    weighted = pd.DataFrame(weighted)
    return weighted


def execute(sub):
    extract_brainstem_roi(sub, epi_dir, atlas_dir, out_dir)
    concat_single_rois(sub, out_dir)
    for session in sessions:
        for run in runs:
            try:
                df = extract_cortical_roi(sub, session, run, epi_dir, combined=False)
                for atlas in atlases:
                    print(sub, session, run, atlas)
                    df[atlas] = weighted_average(sub, session, run, atlas, out_dir)
                df.to_csv(join(out_dir, 'weighted', '{0}_{1}_{2}_weighted_rois.csv'.format(sub, session, run)))
            except IndexError:
                print('error {}'.format(sub))


if __name__ == "__main__":
    execute(sys.argv[1])
