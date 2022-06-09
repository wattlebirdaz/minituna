import minituna_v1 as minituna


def objective(trial: minituna.Trial) -> float:
    x = trial.suggest_uniform("x", 0, 10)
    y = trial.suggest_uniform("y", 0, 10)
    if trial.trial_id < 100:
        z = trial.suggest_uniform("z", 0, 10)
    return (x - 3) ** 2 + (y - 5) ** 2


if __name__ == "__main__":
    # 複数の評価値が詰め込まれる。1回の評価がTrialという概念。
    study = minituna.create_study(
        storage=minituna.Storage(),
        sampler=minituna.Sampler(),
    )

    study.optimize(objective, 10)
    study.enqueue_trial({"x": 0.5, "y": 1.0})

    # ↑はこのようなことをやっている。
    # for i in range(10):
    #     --- Running ---
    #     trial_id = storage.create_new_trial()  # storage内部に新しいFrozenTrialが生成
    #     trial = minituna.Trial(trial_id=trial_id)
    #     try:
    #         param = study.pop_waiting_param()
    #         if param:
    #             trial.set_system_attr("fixed_param", param)
    #             evaluation = objective(trial)
    #             ...
    #             return
    #         search_space = study.sampler.infer_relative_search_spaces()   # search_spaceを推論する
    #         relative_params = study.sampler.sample_relative(search_space)
    #
    #         evaluation = objective(trial)  # 中でサンプルされたパラメーターがstorageに保存される
    #         state = "completed"
    #     except minituna.TrialPruned as e:
    #         state = "pruned"
    #     except Exception as e:
    #         state = "failed"
    #         evaluation = None
    #     storage.save_trial_value(trial_id, evalution)  # 評価値を保存する
    #     storage.save_trial_state(trial_id, state)  # 状態を更新

    best_trial = study.best_trial
    print(f"Best trial: value={best_trial.value} params={best_trial.params}")
