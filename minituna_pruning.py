import abc
import copy
import enum
import json
import math
import random
import numpy as np

from typing import Any
from typing import Callable
from typing import cast
from typing import Dict
from typing import List
from typing import Literal
from typing import Optional
from typing import Union

TrialStateType = Literal["running", "completed", "pruned", "failed"]
CategoricalChoiceType = Union[None, bool, int, float, str]


class TrialPruned(Exception):
    ...


class BaseDistribution(abc.ABC):
    @abc.abstractmethod
    def to_internal_repr(self, external_repr: Any) -> float:
        ...

    @abc.abstractmethod
    def to_external_repr(self, internal_repr: float) -> Any:
        ...


class FloatDistribution(BaseDistribution):
    def __init__(self, low: float, high: float, log: bool) -> None:
        self.low = low
        self.high = high
        self.log = log

    def to_internal_repr(self, external_repr: Any) -> float:
        return external_repr

    def to_external_repr(self, internal_repr: float) -> Any:
        return internal_repr


class IntDistribution(BaseDistribution):
    def __init__(self, low: int, high: int) -> None:
        self.low = low
        self.high = high

    def to_internal_repr(self, external_repr: Any) -> float:
        return float(external_repr)

    def to_external_repr(self, internal_repr: float) -> Any:
        return int(internal_repr)


class CategoricalDistribution(BaseDistribution):
    def __init__(self, choices: List[CategoricalChoiceType]) -> None:
        self.choices = choices

    def to_internal_repr(self, external_repr: Any) -> float:
        return self.choices.index(external_repr)

    def to_external_repr(self, internal_repr: float) -> Any:
        return self.choices[int(internal_repr)]


class FrozenTrial:
    def __init__(self, trial_id: int, state: TrialStateType) -> None:
        self.trial_id = trial_id
        self.state = state
        self.value: Optional[float] = None
        self.intermediate_values: Dict[int, float] = {}
        self.internal_params: Dict[str, float] = {}
        self.distributions: Dict[str, BaseDistribution] = {}

    @property
    def is_finished(self) -> bool:
        return self.state != "running"

    @property
    def params(self) -> Dict[str, Any]:
        external_repr = {}
        for param_name in self.internal_params:
            distribution = self.distributions[param_name]
            internal_repr = self.internal_params[param_name]
            external_repr[param_name] = distribution.to_external_repr(internal_repr)
        return external_repr

    @property
    def last_step(self) -> Optional[int]:
        if len(self.intermediate_values) == 0:
            return None
        else:
            return max(self.intermediate_values.keys())


class Operation(enum.Enum):
    CREATE_NEW_TRIAL = 0
    SET_TRIAL_VALUE = 1
    SET_TRIAL_STATE = 2
    SET_TRIAL_PARAM = 3
    SET_TRIAL_INTERMEDIATE_VALUE = 4


class Journal:
    def __init__(self, op: Operation, data: Dict[str, Any]):
        self.op = op
        self.data = data

    def get_op(self) -> Operation:
        return self.op

    def get_data(self) -> Dict[str, Any]:
        return self.data

    def json_serialize(j: "Journal") -> Dict[str, Any]:
        return {"op": j.get_op().value, "data": j.get_data()}

    def json_deserialize(obj: bytes) -> "Journal":
        return Journal(obj["op"], obj["data"])


class JournalStorage:
    def __init__(self) -> None:
        self.logs: List[Journal] = []
        self.trials: List[FrozenTrial] = []
        self.last_created_trial_id = -1
        self.next_op_id = 0

    def create_new_trial(self) -> int:
        self.logs.append(Journal(Operation.CREATE_NEW_TRIAL, {}))
        self._sync()
        return self.last_created_trial_id

    def set_trial_value(self, trial_id: int, value: float) -> None:
        self.logs.append(
            Journal(Operation.SET_TRIAL_VALUE, {"trial_id": trial_id, "value": value})
        )

    def set_trial_state(self, trial_id: int, state: TrialStateType) -> None:
        self.logs.append(
            Journal(Operation.SET_TRIAL_STATE, {"trial_id": trial_id, "state": state})
        )

    def set_trial_param(
        self, trial_id: int, name: str, distribution: BaseDistribution, value: float
    ) -> None:
        self.logs.append(
            Journal(
                Operation.SET_TRIAL_PARAM,
                {
                    "trial_id": trial_id,
                    "name": name,
                    "distribution": str(distribution),
                    "value": value,
                },
            )
        )

    def set_trial_intermediate_value(
        self, trial_id: int, step: int, value: float
    ) -> None:
        self.logs.append(
            Journal(
                Operation.SET_TRIAL_INTERMEDIATE_VALUE,
                {"trial_id": trial_id, "step": step, "value": value},
            )
        )

    def _write_json_to_file(self, j: Dict[str, Any]) -> None:
        with open("myfile.json", "a") as f:
            json.dump(j, f)
            f.write("\n")

    def _sync(self):
        for log in self.logs[self.next_op_id :]:
            op = log.get_op()
            data = log.get_data()

            self._write_json_to_file(Journal.json_serialize(Journal(op, data)))

            if op == Operation.CREATE_NEW_TRIAL:
                trial_id = len(self.trials)
                trial = FrozenTrial(trial_id=trial_id, state="running")
                self.trials.append(trial)
                self.last_created_trial_id = trial_id
                continue
            trial_id = data["trial_id"]
            trial = self.trials[trial_id]
            assert not trial.is_finished, "cannot update finished trials"
            if op == Operation.SET_TRIAL_VALUE:
                trial.value = data["value"]
            elif op == Operation.SET_TRIAL_STATE:
                trial.state = data["state"]
            elif op == Operation.SET_TRIAL_PARAM:
                name = data["name"]
                trial.distributions[name] = data["distribution"]
                trial.internal_params[name] = data["value"]
            elif op == Operation.SET_TRIAL_INTERMEDIATE_VALUE:
                trial.intermediate_values[data["step"]] = data["value"]
            else:
                raise RuntimeError

        self.next_op_id = len(self.logs)

    def get_all_trials(self) -> List[FrozenTrial]:
        self._sync()
        return copy.deepcopy(self.trials)

    def get_trial(self, trial_id: int) -> FrozenTrial:
        self._sync()
        return copy.deepcopy(self.trials[trial_id])

    def get_best_trial(self) -> Optional[FrozenTrial]:
        self._sync()
        completed_trials = [t for t in self.trials if t.state == "completed"]
        best_trial = min(completed_trials, key=lambda t: cast(float, t.value))
        return copy.deepcopy(best_trial)


class Storage:
    def __init__(self) -> None:
        self.trials: List[FrozenTrial] = []

    def create_new_trial(self) -> int:
        trial_id = len(self.trials)
        trial = FrozenTrial(trial_id=trial_id, state="running")
        self.trials.append(trial)
        return trial_id

    def get_all_trials(self) -> List[FrozenTrial]:
        return copy.deepcopy(self.trials)

    def get_trial(self, trial_id: int) -> FrozenTrial:
        return copy.deepcopy(self.trials[trial_id])

    def get_best_trial(self) -> Optional[FrozenTrial]:
        completed_trials = [t for t in self.trials if t.state == "completed"]
        best_trial = min(completed_trials, key=lambda t: cast(float, t.value))
        return copy.deepcopy(best_trial)

    def set_trial_value(self, trial_id: int, value: float) -> None:
        trial = self.trials[trial_id]
        assert not trial.is_finished, "cannot update finished trials"
        trial.value = value

    def set_trial_state(self, trial_id: int, state: TrialStateType) -> None:
        trial = self.trials[trial_id]
        assert not trial.is_finished, "cannot update finished trials"
        trial.state = state

    def set_trial_param(
        self, trial_id: int, name: str, distribution: BaseDistribution, value: float
    ) -> None:
        trial = self.trials[trial_id]
        assert not trial.is_finished, "cannot update finished trials"
        trial.distributions[name] = distribution
        trial.internal_params[name] = value

    def set_trial_intermediate_value(
        self, trial_id: int, step: int, value: float
    ) -> None:
        trial = self.trials[trial_id]
        assert not trial.is_finished, "cannot update finished trials"
        trial.intermediate_values[step] = value


class Trial:
    def __init__(self, study: "Study", trial_id: int):
        self.study = study
        self.trial_id = trial_id
        self.state = "running"

    def _suggest(self, name: str, distribution: BaseDistribution) -> Any:
        storage = self.study.storage

        trial = storage.get_trial(self.trial_id)
        param_value = self.study.sampler.sample_independent(
            self.study, trial, name, distribution
        )
        param_value_in_internal_repr = distribution.to_internal_repr(param_value)
        storage.set_trial_param(
            self.trial_id, name, distribution, param_value_in_internal_repr
        )
        return param_value

    def suggest_float(
        self, name: str, low: float, high: float, log: bool = False
    ) -> float:
        return self._suggest(name, FloatDistribution(low=low, high=high, log=log))

    def suggest_int(self, name: str, low: int, high: int) -> int:
        return self._suggest(name, IntDistribution(low=low, high=high))

    def suggest_categorical(
        self, name: str, choices: List[CategoricalChoiceType]
    ) -> CategoricalChoiceType:
        return self._suggest(name, CategoricalDistribution(choices=choices))

    def report(self, value: float, step: int) -> None:
        self.study.storage.set_trial_intermediate_value(self.trial_id, step, value)

    def should_prune(self) -> bool:
        trial = self.study.storage.get_trial(self.trial_id)
        return self.study.pruner.prune(self.study, trial)


class Sampler:
    def __init__(self, seed: int = None):
        self.rng = random.Random(seed)

    def sample_independent(
        self,
        study: "Study",
        trial: FrozenTrial,
        name: str,
        distribution: BaseDistribution,
    ) -> Any:
        if isinstance(distribution, FloatDistribution):
            if distribution.log:
                log_low = math.log(distribution.low)
                log_high = math.log(distribution.high)
                return math.exp(self.rng.uniform(log_low, log_high))
            else:
                return self.rng.uniform(distribution.low, distribution.high)
        elif isinstance(distribution, IntDistribution):
            return self.rng.randint(distribution.low, distribution.high)
        elif isinstance(distribution, CategoricalDistribution):
            index = self.rng.randint(0, len(distribution.choices) - 1)
            return distribution.choices[index]
        else:
            raise ValueError("unsupported distribution")


class Pruner:
    def __init__(self, n_startup_trials: int = 5, n_warmup_steps: int = 0) -> None:
        self.n_startup_trials = n_startup_trials
        self.n_warmup_steps = n_warmup_steps

    def prune(self, study: "Study", trial: FrozenTrial) -> bool:
        all_trials = study.storage.get_all_trials()
        n_trials = len([t for t in all_trials if t.state == "completed"])

        if n_trials < self.n_startup_trials:
            return False

        last_step = trial.last_step
        if last_step is None or last_step < self.n_warmup_steps:
            return False

        # Median pruning
        others = [
            t.intermediate_values[last_step]
            for t in all_trials
            if last_step in t.intermediate_values
        ]
        median = np.nanmedian(np.array(others))
        return trial.intermediate_values[last_step] > median


class Study:
    def __init__(self, storage: Storage, sampler: Sampler, pruner: Pruner) -> None:
        self.storage = storage
        self.sampler = sampler
        self.pruner = pruner

    def optimize(self, objective: Callable[[Trial], float], n_trials: int) -> None:
        for _ in range(n_trials):
            trial_id = self.storage.create_new_trial()
            trial = Trial(self, trial_id)

            try:
                value = objective(trial)
                self.storage.set_trial_value(trial_id, value)
                self.storage.set_trial_state(trial_id, "completed")
                print(f"trial_id={trial_id} is completed with value={value}")
            except TrialPruned:
                frozen_trial = self.storage.get_trial(trial_id)
                last_step = frozen_trial.last_step
                assert last_step is not None
                value = frozen_trial.intermediate_values[last_step]

                self.storage.set_trial_value(trial_id, value)
                self.storage.set_trial_state(trial_id, "pruned")
                print(
                    f"trial_id={trial_id} is pruned at step={last_step} value={value}"
                )
            except Exception as e:
                self.storage.set_trial_state(trial_id, "failed")
                print(f"trial_id={trial_id} is failed by {e}")

    @property
    def best_trial(self) -> Optional[FrozenTrial]:
        return self.storage.get_best_trial()


def create_study(
    storage: Optional[Storage] = None,
    sampler: Optional[Sampler] = None,
    pruner: Optional[Pruner] = None,
) -> Study:
    return Study(
        storage=storage or JournalStorage(),
        sampler=sampler or Sampler(),
        pruner=pruner or Pruner(),
    )
