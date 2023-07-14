import json
import typing
import warnings
from pathlib import Path
import numpy.typing as npt
from itertools import permutations
import pickle
from datetime import datetime

import numpy as np
import scipy.stats as st
from tqdm import tqdm

from ..GPR.GSKGPR import GSKGPR
from ..FECalc import FECalc

class MultiObjBayOpt():
    def __init__(self, settings_dir: Path) -> None:
        self.settings_dir = Path(settings_dir)
        # load settings dict
        with open(self.settings_dir) as f:
            self.settings = json.load(f)
        # metadata path
        self.metadata_path = Path(self.settings["metadata_dir"])
        # initializations
        self.initiated = False
        self.max_iter = int(self.settings["max_iter"]) if self.settings.get("max_iter", None) is not None else 10
        self.iter = 0 # current iteration
        self.sample_per_iter = int(self.settings["n_sample_per_iter"]) if self.settings.get("n_sample_per_iter", None) is not None else 1
        self.sampled_points = {} # current dict of sampled points
        self.AA_list = self.settings["allowed_AAs"] # list of allowed amino acids
        self.AA_len = int(self.settings["epi_len"]) # length of peptide section on PCC
        self.AA_dict = Path(self.settings["AA_dict_path"]) # path to AA property dict
        self.unexplored_input_space = np.array([]) # unsampled input space
        # GPR training parameters
        self.gpr_alpha = float(self.settings["gpr_alpha"]) if self.settings.get("gpr_alpha", None) is not None else 0.1
        self.gpr_L_list = self.settings["gpr_L_list"] if self.settings.get("gpr_L_list", None) is not None else [2]
        self.gpr_sigma_bounds = self.settings["gpr_sigma_bounds"] if self.settings.get("gpr_sigma_bounds", None) is not None else (1e-20, 1e10)
        # paths
        self.base_dir = Path(self.settings["base_dir"]) # base directory to store files
        self.calc_dir = Path(self.settings["calc_dir"]) # path to free energy calculations' folder
        self.pickle_path = self.base_dir/"BO_backups" # path to backup pickles
        if not self.pickle_path.exists():
            self.pickle_path.mkdir()
        self.report_dir = self.base_dir/"MOBO_report.json" # path to report.json
        self.FECalc_settings_dir = Path(self.settings["FECalc_settings_dir"])

    @classmethod
    def load(cls, filename) -> typing.Self:
        "Load class from a saved pickle file"
        with open(filename, 'rb') as f:
            return pickle.load(f)
    
    def save(self, filename) -> None:
        "Save class to a saved pickle file"
        with open(filename, 'wb') as f:
            pickle.dump(self, f)
        return None
    
    def _write_report(self) -> None: # TODO: add more info to the report...
        with open(self.report_dir) as f:
            old_r = json.load(f)
        
        now = datetime.now()
        dt_string = now.strftime("%d%m%Y_%H%M%S")
        old_r[self.iter] = {"timestamp": f"{dt_string}",
            "sampled": self.sampled_points[self.iter].tolist(),
                           }
        
        with open(self.report_dir, 'w') as f:
            json.dump(old_r, f, indent=2)
        
        return None

    def _update_metadata(self, name: str, sen_E: float, spc_E: float) -> None: # TODO: write data into metadata file
        return None
    
    def _initiate(self) -> None:
        # assign training data
        self.X_train, self.Y_train_sen, self.Y_train_spc = self._read_data(self.metadata_path)
        # initiate GPR models
        self.sen_gpr = GSKGPR(self.X_train, self.Y_train_sen, AA_matrix = self.AA_dict)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.sen_gpr = self.sen_gpr.fit(self.gpr_alpha, self.gpr_L_list, self.gpr_sigma_bounds)

        self.spc_gpr = GSKGPR(self.X_train, self.Y_train_spc, AA_matrix = self.AA_dict)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.spc_gpr = self.spc_gpr.fit(self.gpr_alpha, self.gpr_L_list, self.gpr_sigma_bounds)

        self.input_space = self._get_input_space(self.AA_list, self.AA_len) # complete input space
        self.unexplored_input_space = np.array([x for x in self.input_space if x not in self.X_train]) # complete - init data
        if not self.report_dir.exists():
            with open(self.report_dir, 'w') as f:
                json.dump({}, f, indent=1)
        # update initiations status
        self.initiated = True
        return None

    def _read_data(self, metadata_dir: Path) -> tuple:
        """
        reads training data from metadata.json and creates X and Y arrays for training

        Args:
            metadata_dir (Path): Path to metadata.json

        Returns:
            tuple: training data
        """
        with open(metadata_dir) as f:
            metadata = json.load(f)
        # read X and Y from metadata file
        X_train = np.array(list(metadata.keys()))
        Y_train_sen = np.array([val['FE_b'] for _, val in metadata.items()])
        Y_train_spc = np.array([val['FE_s'] for _, val in metadata.items()])
        return X_train, Y_train_sen, Y_train_spc

    def _get_input_space(self, AA_list: typing.Iterable, AA_len: int) -> npt.ArrayLike:
        """
        Calculates all permutations of `AA_len` peptides from amino acids in `AA_list`.

        Inputs:
            AA_list (Iterable): list of allowed amino acids
            AA_len (int): length of peptide section

        Returns:
            npt.ArrayLike: all permutations of the allowed amino acids
        """
        return np.array(["".join(perm) for perm in permutations(AA_list, AA_len)])
    
    def _update_state(self) -> None:
        """
        Update object state to include new data points and exclude data points already in the training set.
        """
        # update iteration
        self.iter += 1
        # assign new training data
        self.X_train, self.Y_train_sen, self.Y_train_spc = self._read_data(self.metadata_path)
        # update GPR models
        self.sen_gpr = GSKGPR(self.X_train, self.Y_train_sen, AA_matrix = self.AA_dict)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.sen_gpr = self.sen_gpr.fit(self.gpr_alpha, self.gpr_L_list, self.gpr_sigma_bounds)

        self.spc_gpr = GSKGPR(self.X_train, self.Y_train_spc, AA_matrix = self.AA_dict)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.spc_gpr = self.spc_gpr.fit(self.gpr_alpha, self.gpr_L_list, self.gpr_sigma_bounds)
            
        # update unexplored region
        explored = []
        for samples in self.sampled_points.values():
            explored.extend(samples)
        explored = np.concatenate((self.X_train, explored))
        self.unexplored_input_space = np.array([x for x in self.input_space if x not in explored])
        return None
        
    def _EI_acquisition(self, current_max: float, means: npt.ArrayLike, stds: npt.ArrayLike, alpha: float) -> npt.ArrayLike:
        """
        Expected Improvement acquisition function.

        Args:
            means (npt.ArrayLike): means of data points in shape (n, )
            stds (npt.ArrayLike): standard deviation of data points in shape (n, )
            alpha (float): alpha hyperparameter

        Returns:
            tuple: argmax of EI and the Expected Improvment acquisition function values of sizes (1, (n, ))
        """
        # calculate all EI values
        zs = (means - current_max*np.ones_like(means) - alpha*np.ones_like(means))/stds
        EI_vals = zs * stds * st.norm.cdf(zs) + stds * st.norm.pdf(zs)
        # set all negative values to zero
        EI_vals[EI_vals<0] = 0
        # find the argmax of EI_vals
        arg_max = np.argmax(EI_vals)
        return arg_max, EI_vals

    def _get_weights(self, bounds: tuple, size: int) -> npt.ArrayLike:
        """
        Sample a uniform distribution on `bounds` to get weights for scalarization function. Returned weights are NORM 1 NORMALIZED.

        Args:
            bounds (tuple): box defining the bounds to sample weights from. Should be in format `((a_1, b_1), (a_2, b_2))`
            size (int): number of sampled weights to return

        Returns:
            npt.ArrayLike: scalarization weights of shape (2, `size`), format [[l_11, l_12, ...], [l_21, l_22, ...]]
        """
        lambda1_bounds, lambda2_bounds = bounds
        lambda1s = np.random.uniform(*lambda1_bounds, size=size)
        lambda2s = np.random.uniform(*lambda2_bounds, size=size)
        lambdas = np.column_stack((lambda1s, lambda2s))
        row_sums = lambdas.sum(axis=1, keepdims=True)
        lambdas /= row_sums
        return lambdas

    def _lin_scalarization(self, objs: npt.ArrayLike, weights: npt.ArrayLike) -> float:
        """
        linear scalarization of objective functions.

        Args:
            objs (npt.ArrayLike): objective function values of shape (n_samples, n, 2)
            weights (npt.ArrayLike): linearization weights of shape (n_samples, n, 2)

        Returns:
            float: scalarization of the objectives functions of shape (n_samples, n)
        """
        weighted_objs = objs * weights
        lin_val = np.sum(weighted_objs, axis=-1)
        return lin_val
    
    def _get_samples(self, lambdas: npt.ArrayLike) -> npt.ArrayLike:
        """
        Get the argmax of the linearization that maximizes the acquisition function using sampled lambdas

        Args:
            lambdas (npt.ArrayLike): _description_

        Returns:
            npt.ArrayLike: _description_
        """
        # calculate surrogate for all points in the unexplored input space
        sen_mean, sen_std = self.sen_gpr.predict(self.unexplored_input_space, return_std=True)
        spc_mean, spc_std = self.spc_gpr.predict(self.unexplored_input_space, return_std=True)
        # get acquisition function values for all the points
        _, sen_aqs = self._EI_acquisition(self.Y_train_sen.max(), sen_mean, sen_std, alpha=0.3) # (n, )
        _, spc_aqs = self._EI_acquisition(self.Y_train_spc.max(), spc_mean, spc_std, alpha=0.3) # (n, )
        objs = np.column_stack((sen_aqs, spc_aqs)) # (n, 2)
        objs = np.tile(objs, [self.sample_per_iter, 1, 1]) # (n_sample, n, 2)
        # scalarization
        lambdas = np.reshape(lambdas, (self.sample_per_iter, 1, -1)) # (n_sample, 1, 2)
        weights = np.tile(lambdas, [1, objs.shape[1], 1]) # (n_sample, n, 2)
        scalars = self._lin_scalarization(objs, weights) # (n_sample, n)
        return np.argmax(scalars, axis=-1) # (n_sample, )
    
    def _evaluate(self, samples: npt.ArrayLike) -> None: # NOTE: FOR DEBUG ONLY
        with open("/project/andrewferguson/armin/HTVS_Fentanyl/MOBO/TEST/FAKE_metadata.JSON") as f:
            dataset = json.load(f)

        with open(self.metadata_path) as f:
            metadata = json.load(f)
        
        for sample in samples:
            metadata[sample] = {"FE_b": dataset[sample]["FE_b"],
                                "FE_s": dataset[sample]["FE_s"]}
        
        with open(self.metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        return None
    
    def __evaluate(self, samples: npt.ArrayLike) -> None: # NOTE: Not tested. Add a check so it doesn't rerun calcualtions
        """
        Submit FE calculations for samples in `samples` and update the metadata file with the results.

        Args:
            samples (npt.ArrayLike): list of samples selected by the MOBO

        Returns:
            None
        """
        for sample in samples:
            # get sensitivity
            FEN_FE = FECalc(sample, "FEN", self.calc_dir/f"{sample}_FEN", self.FECalc_settings_dir)
            sen_FE = -FEN_FE.get_FE()
            # get specificity
            FEN_FE = FECalc(sample, "DEC", self.calc_dir/f"{sample}_DEC", self.FECalc_settings_dir)
            spc_FE = FEN_FE.get_FE() + sen_FE
            # update metadata file
            self._update_metadata(sample, sen_FE, spc_FE)
        return None

    def optimize(self, bounds: tuple) -> None:
        # initiate if not initiated already
        if not self.initiated:
            self._initiate()

        for iter in tqdm(range(self.max_iter)):
            # sample scalarization weights
            lambdas = self._get_weights(bounds=bounds, size=self.sample_per_iter) # (n_sample, 2)
            # get samples by maximizing acquisition function
            samples = self._get_samples(lambdas=lambdas) # indeces of samples (n_samples, )
            # evaluate sen and spc for new samples
            self._evaluate(self.unexplored_input_space[samples])
            # update sampled sites
            self.sampled_points[self.iter] = self.input_space[list(set(samples))]
            # save current model
            now = datetime.now()
            dt_string = now.strftime("%d%m%Y_%H%M%S")
            # write report
            self._write_report()
            # save model to pckl
            # self.save(self.pickle_path/(f"{self.iter}_"+dt_string+".pckl")) ####### <------- RE-ENABLE FOR ACTUAL RUN
            # update object state
            self._update_state()
        return None