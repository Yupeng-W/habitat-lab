import argparse
import os
import random
import string
import uuid


def zsc_eval(args, add_opts):
    rnd_id = random.choice(string.ascii_uppercase) + str(uuid.uuid4())[:8]

    for plan_idx in range(args.num_plans):
        run_cmd = f"python habitat_baselines/run.py --config-name=experiments_hab3/eval_zsc_kinematic_oracle.yaml habitat_baselines.rl.policy.agent_1.hierarchical_policy.high_level_policy.plan_idx={plan_idx} {add_opts} habitat_baselines.wb.group={rnd_id}"
        print(f"RUNNING {run_cmd}")
        os.system(run_cmd)
        if args.debug:
            break

    if args.debug:
        return

    learned_agents = args.learned_agents.split(",")
    for learned_agent in learned_agents:
        run_cmd = f'python habitat_baselines/run.py --config-name=experiments_hab3/pop_play_kinematic_oracle_humanoid_spot_fp.yaml habitat_baselines.rl.agent.load_type1_pop_ckpts=[{learned_agent}] {add_opts} habitat_baselines.wb.group={rnd_id} habitat_baselines.rl.agent.num_pool_agents_per_type="[1,1]" habitat_baselines.evaluate=True'
        print(f"RUNNING {run_cmd}")
        os.system(run_cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # For tidy-house style task there are 5 plans.
    parser.add_argument("--num-plans", type=int, default=5)
    parser.add_argument(
        "--learned-agents",
        type=str,
        default="",
        help="Comma separated list of checkpoints of holdout learned agents.",
    )
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "opts",
        default=None,
        nargs=argparse.REMAINDER,
        help="Modify config options from command line",
    )
    args = parser.parse_args()
    add_opts = " ".join(args.opts)

    zsc_eval(args, add_opts)
