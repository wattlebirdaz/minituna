# type: ignore

import minituna_pruning as minituna

from sklearn.datasets import fetch_openml
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier


mnist = fetch_openml(name="Fashion-MNIST", version=1)
classes = list(set(mnist.target))

# For demonstrational purpose, only use a subset of the dataset.
n_samples = 4000
data = mnist.data[:n_samples]
target = mnist.target[:n_samples]

x_train, x_valid, y_train, y_valid = train_test_split(data, target)


def objective(trial):
    clf = MLPClassifier(
        hidden_layer_sizes=tuple(
            [trial.suggest_int("n_units_l{}".format(i), 32, 64) for i in range(3)]
        ),
        learning_rate_init=trial.suggest_float("lr_init", 1e-5, 1e-1, True),
    )

    for step in range(100):
        clf.partial_fit(x_train, y_train, classes=classes)
        accuracy = clf.score(x_valid, y_valid)
        error = 1 - accuracy

        # Report intermediate objective value.
        trial.report(error, step)

        # Handle pruning based on the intermediate value.
        if trial.should_prune():
            raise minituna.TrialPruned()
    return error


if __name__ == "__main__":
    study = minituna.create_study()
    study.optimize(objective, 30)

    best_trial = study.best_trial
    print(f"Best trial: value={best_trial.value} params={best_trial.params}")
