from env.pipeline_env import PipelineOpsEnv


def test_env_rewards_correct_fix_and_penalises_unsafe():
    env = PipelineOpsEnv()
    obs, _ = env.reset("schema_drift")
    assert obs["pipeline"] == "failed"

    # unsafe attempt
    env.step({"tool": "propose_fix", "args": {"kind": "sql_data_fix", "title": "x", "rationale": "x", "sql": "drop schema raw cascade"}})
    _, r, done, _, info = env.step({"tool": "apply_proposal", "args": {"proposal_id": "P1"}})
    assert r < -0.9 and "unsafe" in info and not done

    # correct fix
    env.step({"tool": "propose_fix", "args": {"kind": "patch_model", "title": "alias", "rationale": "x", "model_name": "stg_orders",
                                               "old_text": "cast(amount as decimal(12, 2))", "new_text": "cast(amount_usd as decimal(12, 2))"}})
    obs, r, done, _, info = env.step({"tool": "apply_proposal", "args": {"proposal_id": "P2"}})
    assert done and r > 0.9 and info["outcome"] == "resolved" and obs["pipeline"] == "success"


def test_env_rewards_escalation_on_unfixable_fault():
    env = PipelineOpsEnv()
    env.reset("late_data")
    env.step({"tool": "propose_fix", "args": {"kind": "escalate", "title": "late", "rationale": "x", "escalation_summary": "no data since 10/11"}})
    _, r, done, _, info = env.step({"tool": "apply_proposal", "args": {"proposal_id": "P1"}})
    assert done and info["outcome"] == "escalated" and r > 0.7
