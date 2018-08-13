import pandas as pdimport numpy as npfrom os.path import joinfrom decim.fmri_workflow import BehavDataframe as fafrom collections import defaultdictfrom decim import pupil_grating_correct as pgcfrom joblib import Memorycachedir = '/Users/kenohagena/Flexrule/cachedir'memory = Memory(cachedir=cachedir, verbose=0)summary = pd.read_csv('/Users/kenohagena/Flexrule/fmri/analyses/bids_stan_fits/summary_stan_fits.csv')def baseline(grating, choice, length=1000):    baseline = np.matrix((grating.loc[:, 0:length].mean(axis=1))).T    return pd.DataFrame(np.matrix(grating) - baseline), pd.DataFrame(np.matrix(choice) - baseline), baselineclass Choiceframe(object):    def __init__(self, subject, session, run, task, flex_dir, BehavFrame, PupilFrame, BrainstemRois):        '''        Initialize        '''        self.subject = subject        self.session = session        self.run = run        self.task = task        self.flex_dir = flex_dir        self.BehavFrame = BehavFrame        self.PupilFrame = PupilFrame        self.BrainstemRois = BrainstemRois    def choice_behavior(self):        df = self.BehavFrame        df.onset = df.onset.astype(float)        df = df.sort_values(by='onset')        choices = pd.DataFrame({'rule_response': df.rule_resp.dropna(how='any').values.astype(int),                                'rt': df.loc[df.event == 'CHOICE_TRIAL_RESP'].rt.values.astype(float),                                'stimulus': df.stim_id.dropna(how='any').values,                                'response': df.loc[df.response == True, 'value'].values.astype(int),                                'reward': df.loc[df.event == 'CHOICE_TRIAL_RESP'].reward.values.astype(int),                                'onset': df.loc[df.event == 'CHOICE_TRIAL_ONSET'].onset.values.astype(float)})        if self.task == 'inference':            choices['trial_id'] = df.loc[df.event == 'CHOICE_TRIAL_ONSET'].trial_id.values.astype(int)            choices['accumulated_belief'] = df.loc[df.event == 'CHOICE_TRIAL_ONSET'].belief.values.astype(float)            choices['rewarded_rule'] = df.loc[df.event == 'CHOICE_TRIAL_ONSET'].gen_side.values + 0.5        elif self.task == 'instructed':            choices['trial_id'] = np.arange(1, len(choices) + 1, 1)            choices['accumulated_belief'] = np.nan            choices['rewarded_rule'] = df.loc[df.event == 'CHOICE_TRIAL_ONSET'].rewarded_rule.values        self.choice_behavior = choices    def points(self, n=20):        '''        Add last n points before choice onset.        '''        df = self.BehavFrame        points = df.loc[(df.event == 'GL_TRIAL_LOCATION')]        p = []        for i, row in self.choice_behavior.iterrows():            trial_points = points.loc[points.onset.astype('float') < row.onset]            if len(trial_points) < 20:                trial_points = np.full(20, np.nan)            else:                trial_points = trial_points.value.values[len(trial_points) - 20:len(trial_points)]            p.append(trial_points)        points = pd.DataFrame(p)        points['trial_id'] = self.choice_behavior.trial_id.values        self.point_kernels = points    def choice_pupil(self, artifact_threshhold=.2, tw=4500):        '''        Takes existing pupilframe and makes choicepupil frame.        If there is no existing pupilframe, a new one is created.        '''        df = self.PupilFrame.loc[:, ['message', 'biz', 'message_value', 'blink', 'run', 'trial_id']]        pupil_grating_lock = []        pupil_choice_lock = []        pupil_parameters = []        blinks_choice_lock = []        for choice_trial in df.loc[df.message == "CHOICE_TRIAL_ONSET"].index:            '''            Extract gratinglocked pupilresponse, choicelocked pupil response & choice parameters            '''            onset = choice_trial            if len(df.iloc[onset: onset + 3500, :].loc[df.message == 'RT', 'message_value']) == 0:                continue            else:                response_time = df.iloc[onset - 1000: onset + 3500, :].loc[df.message == 'RT', 'message_value']                pupil_grating_lock.append(df.loc[np.arange(onset - 1000, onset + tw - 1000).astype(int), 'biz'].values)                pupil_parameters.append([df.iloc[onset - 1000: onset + 3500, :].loc[df.message == 'RT', 'message_value'].values,                                         df.loc[np.arange(onset, onset + response_time + 1500), 'blink'].mean(),                                         df.loc[onset, 'trial_id']])                pupil_choice_lock.append(df.loc[np.arange(onset + response_time - 1000, onset + response_time + 1500).astype(int), 'biz'].values)                blinks_choice_lock.append(df.loc[np.arange(onset + response_time - 1000, onset + response_time + 1500).astype(int), 'blink'].values)        pupil_grating_lock = pd.DataFrame(pupil_grating_lock)        pupil_choice_lock = pd.DataFrame(pupil_choice_lock)        grat, choice, bl = baseline(pupil_grating_lock, pupil_choice_lock)        self.blinks_choice_lock = pd.DataFrame(blinks_choice_lock)        self.pupil_grating_lock = grat        self.pupil_choice_lock = choice        self.pupil_parameters = pd.DataFrame(pupil_parameters)        self.pupil_parameters.columns = (['rt', 'blink', 'trial_id'])        self.pupil_parameters['TPR'] = self.pupil_choice_lock.mean(axis=1)    def fmri_epochs(self, basel=2000, te=6):        roi = self.BrainstemRois        roi = roi.loc[:, ['aan_dr', 'basal_forebrain_4',                          'basal_forebrain_123', 'LC_standard', 'NAc', 'SNc',                          'VTA']]        dt = pd.to_timedelta(roi.index.values * 1900, unit='ms')        roi = roi.set_index(dt)        target = roi.resample('100ms').mean().index        roi = pd.concat([fa.interp(dt, roi[c], target) for c in roi.columns], axis=1)        behav = self.choice_behavior        onsets = behav.onset.values        evoked_run = defaultdict(list)        for onset in onsets:            cue = pd.Timedelta(onset, unit='s').round('ms')            bl = pd.Timedelta(basel, unit='ms')            baseline = roi.loc[cue - bl: cue + bl].mean()            task_evoked = roi.loc[cue - bl: cue + bl * te] - baseline            for col in task_evoked.columns:                evoked_run[col].append(task_evoked[col].values)        for key, values in evoked_run.items():            df = pd.DataFrame(values)            evoked_run[key] = df        self.roi_epochs = evoked_run    def merge(self):        '''        Merge everything. And Save.        '''        self.pupil_grating_lock.columns = pd.MultiIndex.from_product([['pupil'], ['gratinglock'],                                                                      range(self.pupil_grating_lock.shape[1])],                                                                     names=['source', 'type', 'name'])        self.pupil_choice_lock.columns = pd.MultiIndex.from_product([['pupil'], ['choicelock'], range(self.pupil_choice_lock.shape[1])], names=['source', 'type', 'name'])        self.pupil_parameters.columns = pd.MultiIndex.from_product([['pupil'], ['parameters'], self.pupil_parameters.columns], names=['source', 'type', 'name'])        self.choice_behavior.columns = pd.MultiIndex.from_product([['behavior'], ['parameters'], self.choice_behavior.columns], names=['source', 'type', 'name'])        self.point_kernels.columns = pd.MultiIndex.from_product([['behavior'], ['points'], range(self.point_kernels.shape[1])], names=['source', 'type', 'name'])        self.blinks_choice_lock.columns = pd.MultiIndex.from_product([['pupil'], ['choice_interpol'], range(self.blinks_choice_lock.shape[1])], names=['source', 'type', 'name'])        master = pd.concat([self.pupil_choice_lock,                            self.pupil_grating_lock,                            self.pupil_parameters,                            self.choice_behavior,                            self.point_kernels], axis=1)        master = master.set_index([master.pupil.parameters.trial_id])        singles = []        for key, frame in self.roi_epochs.items():            frame.columns = pd.MultiIndex.from_product([['fmri'], [key], frame.columns], names=['source', 'type', 'name'])            singles.append(frame)        fmri = pd.concat(singles, axis=1)        self.master = pd.merge(fmri.set_index(master.index, drop=True).reset_index(), master.reset_index())@memory.cachedef execute(subject, session, run, task, flex_dir, BehavFrame, PupilFrame, BrainstemRois):    c = Choiceframe(subject, session, run, task, flex_dir, BehavFrame, PupilFrame, BrainstemRois)    c.choice_behavior()    if task == 'inference':        c.points()    elif task == 'instructed':        c.point_kernels = pd.DataFrame(np.zeros((c.choice_behavior.shape[0], 20)))    c.choice_pupil()    c.fmri_epochs()    c.merge()    return c.master@memory.cachedef defit_clean(session_master):    clean = session_master.loc[session_master.pupil.parameters.blink == 0]    grating = clean.pupil.gratinglock    '''    Fit    '''    fit = pgc.FitTmax(grating)    err = []    ts = []    for tmax in np.arange(-0.3, 0, 0.01):        err.append(fit.predict_tmax(tmax)[0])        ts.append(tmax)    err = np.array(err)    tmax = ts[np.argmin(err)]    pred = fit.predict_tmax(tmax=ts[np.argmin(err)])[1]    '''    Plot error and check best fit...    f, ax = plt.subplots(1, 2, figsize=(9, 4))    ax[0].plot(ts, err)    ax[0].set(ylim=[0, 100])    ax[1].plot(pred)    ax[1].plot(grating.mean().values)    '''    '''    Defit    '''    grating = grating - pred    grating.columns = pd.MultiIndex.from_product([['pupil'], ['grating_defitted'], range(grating.shape[1])], names=['source', 'type', 'name'])    clean = pd.concat([clean, grating], axis=1)    choicelock = []    for i, row in clean.iterrows():        rt = int(row.behavior.parameters.rt * 1000)        choicelock.append(row.pupil.grating_defitted[rt:rt + 2500].values)    choicelock = pd.DataFrame(choicelock)    choicelock.columns = pd.MultiIndex.from_product([['pupil'], ['choicelock_defitted'], range(choicelock.shape[1])], names=['source', 'type', 'name'])    choicelock.index = grating.index    clean = pd.concat([clean, choicelock], axis=1)    return clean__version__ = '2.0''''2.0-Input linear pupilframes-recquires BIDS1.2-triallocked period now 1000ms before offset and total of 4500ms-if rt > 2000ms choicelocked is set to np.nan'''