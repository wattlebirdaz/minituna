import copy
import random

from typing import Callable
from typing import cast
from typing import Dict
from typing import List
from typing import Literal
from typing import Optional


TrialStateType = Literal["running", "completed", "failed"]


# Trialのストレージ上での表現
# suggest_uniform() のようなパラメーターをサンプルするAPIを提供せず、
class FrozenTrial:
    def __init__(self, trial_id: int, state: TrialStateType) -> None:
        self.trial_id = trial_id  # identifier
        self.state = state        # 目的関数の実行状態: Running, Complete, Failed
        self.value: Optional[float] = None  # 評価値
        self.params: Dict[str, float] = {}  # サンプルされたパラメーター  {"x": 2.2, "y": 8.0}

    @property
    def is_finished(self) -> bool:
        return self.state != "running"


class Storage:
    def __init__(self) -> None:
        self.trials: List[FrozenTrial] = []

    def create_new_trial(self) -> int:
        trial_id = len(self.trials)
        trial = FrozenTrial(trial_id=trial_id, state="running")
        self.trials.append(trial)
        return trial_id

    def get_trial(self, trial_id: int) -> FrozenTrial:
        return copy.deepcopy(self.trials[trial_id])

    def get_best_trial(self) -> Optional[FrozenTrial]:
        completed_trials = [t for t in self.trials if t.state == "completed"]
        best_trial = min(completed_trials, key=lambda t: cast(float, t.value))
        return copy.deepcopy(best_trial)

    def set_trial_value(self, trial_id: int, value: float) -> None:
        # 評価値を設定するメソッド
        trial = self.trials[trial_id]
        assert not trial.is_finished, "cannot update finished trials"
        trial.value = value

    def set_trial_state(self, trial_id: int, state: TrialStateType) -> None:
        # 状態を更新するメソッド
        trial = self.trials[trial_id]
        assert not trial.is_finished, "cannot update finished trials"
        trial.state = state

    def set_trial_param(self, trial_id: int, name: str, value: float) -> None:
        # パラメーター name は Trial trial_id において、値 value がサンプルされました。
        trial = self.trials[trial_id]
        assert not trial.is_finished, "cannot update finished trials"
        trial.params[name] = value


class Trial:
    def __init__(self, study: "Study", trial_id: int) -> None:
        self.study = study
        self.trial_id = trial_id
        self.state = "running"

    def suggest_uniform(self, name: str, low: float, high: float) -> float:
        trial = self.study.storage.get_trial(self.trial_id)
        distribution: Dict[str, float] = {"low": low, "high": high}
        param = self.study.sampler.sample_independent(
            self.study, trial, name, distribution
        )
        self.study.storage.set_trial_param(self.trial_id, name, param)
        return param


class Sampler:
    def __init__(self, seed: int = None) -> None:
        self.rng = random.Random(seed)

    def infer_relative_search_space(
        self, study: "optuna.Study", trial: "optuna.trial.FrozenTrial"
    ) -> Dict[str, BaseDistribution]:
        # 目的関数の評価が終わったらTrialの一覧をとってくる
        completed_trials = study.storage.get_all_trials(state="Complete")
        intersection = set(completed_trials[0])  # ("x", "y")
        for trial in completed_trials:
            # trial.distributions {"x": Uniform..., "y": Categorical...}
            intersection.intersection(set(trial.distributions))

        return intersection  # {"x": ..., "y": ...}

    def sample_relative(
        self,
        study: "Study",
        trial: FrozenTrial,
        search_space: Dict[str, BaseDistribution],
    ):
        return {"x": 0.5, "y": 8.0}

    def sample_independent(
        self,
        study: "Study",
        trial: FrozenTrial,
        name: str,
        distribution: Dict[str, float],
    ) -> float:
        ...


class Study:
    def __init__(self, storage: Storage, sampler: Sampler) -> None:
        self.storage = storage
        self.sampler = sampler

    def optimize(self, objective: Callable[[Trial], float], n_trials: int) -> None:
        for _ in range(n_trials):
            trial_id = self.storage.create_new_trial()
            trial = Trial(self, trial_id)  # Trial(Study, trial_id) - studyにはstorageとsamplerがある。

            try:
                value = objective(trial)
                self.storage.set_trial_value(trial_id, value)
                self.storage.set_trial_state(trial_id, "completed")
                print(f"trial_id={trial_id} is completed with value={value}")
            except Exception as e:
                self.storage.set_trial_state(trial_id, "failed")
                print(f"trial_id={trial_id} is failed by {e}")

    @property
    def best_trial(self) -> Optional[FrozenTrial]:
        return self.storage.get_best_trial()


def create_study(
    storage: Optional[Storage] = None,
    sampler: Optional[Sampler] = None,
) -> Study:
    return Study(
        storage=storage or Storage(),
        sampler=sampler or Sampler(),
    )
