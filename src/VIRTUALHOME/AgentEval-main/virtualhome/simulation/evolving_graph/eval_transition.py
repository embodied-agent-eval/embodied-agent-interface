import json
import sys

sys.path.append("../simulation")

import re
import copy
import sys
import os
import os.path as osp
import copy
import ast
import random
import math
from collections import defaultdict

import evolving_graph.utils as utils
from evolving_graph.eval_utils import *
from pddlgym_planners.fd import FD
from visualization import *
from logic_score import *


model_name = "gpt-3.5-turbo-0125"

def tm_input_preparation():
    helm_prompt_list = []

    dataset = "virtualhome"
    resource_root = (
        f"/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/{dataset}"
    )

    pddl_root = osp.join(resource_root, "pddl_files")
    pddl_problem_dir = osp.join(resource_root, "problem_pddl")
    os.makedirs(pddl_root, exist_ok=True)
    os.makedirs(pddl_problem_dir, exist_ok=True)

    success_dict_path = osp.join(resource_root, "success_task.json")
    pred2category_path = osp.join(resource_root, "predicates_category.json")
    id2action_path = osp.join(resource_root, "id2action.json")
    gold_action_path = osp.join(resource_root, "gold_action.json")

    task_dict_dir = "/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/task_state_updated.json"
    prompt_path = (
        "/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/prompts/operator_prompt_complete.txt"
    )
    helm_prompt_path = "/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/helm/helm_prompt/operator_evaluation_vh_final_complete.json"
    # pddl_problem_dir = '/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/pddl_files/virtualhome'

    pred2category = json.load(open(pred2category_path, "r"))
    task_dict = json.load(open(task_dict_dir, "r"))
    success_file_id = json.load(open(success_dict_path, "r"))
    predicate_type = set(list(pred2category.values()))
    id2action = json.load(open(id2action_path, "r"))
    gold_action_dict = json.load(open(gold_action_path, "r"))

    task_dict = task_dict["scene_1"]

    for task_name, task_detail in task_dict.items():
        if task_name in ["Wash dishes by hand", "Write an email", "Wash hands"]:
            continue
        print(f"task name is {task_name}")
        # if task_name not in ['Put groceries in Fridge', 'Wash clothes']:
        #     continue
        task_name = "_".join(task_name.split())
        task_problem_dir = os.path.join(pddl_problem_dir, task_name)

        task_list = task_detail["task_file_list"]
        task_list_ans_list = task_detail["task_file_list_with_ans"]
        print(f"{task_name} has list {task_list}")

        for file_id in task_list:
            if os.path.exists(success_dict_path):
                if file_id not in success_file_id:
                    continue
            # if file_id != '850_1':
            #     continue
            ans_id = get_candidate_id(file_id, task_list_ans_list)
            if ans_id == -1:
                continue
            
            problem_path = os.path.join(task_problem_dir, f"{file_id}.pddl")
            problem_file = open(problem_path, "r").read()

            gold_actions_name = id2action[file_id]
            action_handlers = ""
            for action_name in gold_actions_name:
                action_param = gold_action_dict[action_name]["action_parameters"]
                action_handlers += f"(:action {action_name}\n  :parameters {action_param}\n  :precondition ()\n  :effect ()\n)\n"

            prompt = open(prompt_path, "r").read()
            prompt = prompt.replace("<problem_file>", problem_file)
            prompt = prompt.replace("<action_handlers", action_handlers)
            helm_prompt_list.append(
                {"identifier": f"{file_id}", "llm_prompt": f"{prompt}"}
            )

    # save helm prompt
    json.dump(helm_prompt_list, open(helm_prompt_path, "w"), indent=4)


def llm_prediction():
    
    helm_prompt_path = "/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/helm/helm_prompt/operator_evaluation_vh_final_complete.json"
    helm_output_path = f"/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/helm/helm_output/operator_evaluation_vh_final_complete_{model_name}.json"
    helm_output = []
    helm_prompt = json.load(open(helm_prompt_path, "r"))
    for prompt_dict in helm_prompt:
        id = prompt_dict["identifier"]
        prompt = prompt_dict["llm_prompt"]
        print(f"GPT starts prediction: {id}", flush=True)
        predicted_action = get_gpt_output(prompt, model_name, temperature=1)
        helm_output.append({"identifier": id, "llm_output": predicted_action})
    json.dump(helm_output, open(helm_output_path, "w"), indent=4)


def evaluate_operator_succ():
    print("Enter function!")
    visualization = False
    save_results = True

    dataset = "virtualhome"
    resource_root = (
        f"/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/{dataset}"
    )
    # load LLM output
    helm_output_path = f"/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/helm/helm_output/operator_evaluation_vh_final_complete_{model_name}.json"
    helm_output = json.load(open(helm_output_path, "r"))

    # indexing path
    id2action_path = osp.join(resource_root, "id2action.json")
    id2category_path = osp.join(resource_root, "id2category_2.json")
    id2task_path = osp.join(resource_root, "id2task.json")
    id2predicate_path = osp.join(resource_root, "id2predicate.json")
    success_dict_path = osp.join(resource_root, "success_task.json")

    # evaluation path
    domain_path = osp.join(resource_root, f"{dataset}.pddl")
    domain_pd_path = osp.join(resource_root, f"{dataset}_pd.pddl")
    gold_action_path = osp.join(resource_root, "gold_action.json")
    pred2category_path = osp.join(resource_root, "predicates_category.json")

    # save path and figure path
    save_root = f"/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/output/operator_eval_{model_name}"
    if not os.path.exists(save_root):
        os.makedirs(save_root)
    fig_root = os.path.join(save_root, "fig")
    if not os.path.exists(fig_root):
        os.makedirs(fig_root)
    pddl_root = osp.join(resource_root, "pddl_files")
    pddl_problem_dir = osp.join(resource_root, "problem_pddl")
    os.makedirs(pddl_root, exist_ok=True)
    os.makedirs(pddl_problem_dir, exist_ok=True)

    precond_predicate_type_res_dict_path = os.path.join(
        save_root, "precond_predicate_type_res_dict.json"
    )
    precond_predicate_type_res_fig_path = os.path.join(
        fig_root, "precond_predicate_type_res_dict.png"
    )
    precond_action_type_dict_path = os.path.join(save_root, "precond_action_type_dict.json")
    precond_action_type_fig_path = os.path.join(fig_root, "precond_action_type_dict.png")
    effect_predicate_type_res_dict_path = os.path.join(
        save_root, "effect_predicate_type_res_dict.json"
    )
    effect_predicate_type_res_fig_path = os.path.join(
        fig_root, "effect_predicate_type_res_dict.png"
    )
    effect_action_type_dict_path = os.path.join(save_root, "effect_action_type_dict.json")
    effect_action_type_fig_path = os.path.join(fig_root, "effect_action_type_dict.png")
    full_predicate_type_res_dict_path = os.path.join(
        save_root, "full_predicate_type_res_dict.json"
    )
    full_predicate_type_res_fig_path = os.path.join(
        fig_root, "full_predicate_type_res_dict.png"
    )
    full_action_type_dict_path = os.path.join(save_root, "full_action_type_dict.json")
    full_action_type_fig_path = os.path.join(fig_root, "full_action_type_dict.png")

    precond_predicate_res_dict_path = os.path.join(save_root, "precond_predicate_res_dict.json")
    effect_predicate_res_dict_path = os.path.join(save_root, "effect_predicate_res_dict.json")
    full_predicate_res_dict_path = os.path.join(save_root, "full_predicate_res_dict.json")
    
    success_by_task_type_dict_path = os.path.join(save_root, "success_by_task_type_dict.json")

    task_variate_control_by_type_path = os.path.join(save_root, "task_variate_control_by_type.json")
    task_variate_control_precond_by_type_path = os.path.join(save_root, "task_variate_control_precond_by_type.json")
    task_variate_control_effect_by_type_path = os.path.join(save_root, "task_variate_control_effect_by_type.json")
    action_variate_control_path = os.path.join(save_root, "action_variate_control.json")
    action_variate_control_precond_path = os.path.join(save_root, "action_variate_control_precond.json")
    action_variate_control_effect_path = os.path.join(save_root, "action_variate_control_effect.json")

    per_task_res_path = os.path.join(save_root, "per_task_res.json")

    # load indexing dict
    id2action = json.load(open(id2action_path, "r"))
    id2category = json.load(open(id2category_path, "r"))
    id2task = json.load(open(id2task_path, "r"))
    id2predicate = json.load(open(id2predicate_path, "r"))
    success_file_id = json.load(open(success_dict_path, "r"))
    pred2category = json.load(open(pred2category_path, "r"))

    categories_set = {
        "object states",
        "object affordance",
        "object orientation",
        "object tools",
        "spatial relations",
        "non-spatial relations",
    }
    action_set = set()
    for action_list in id2action.values():
        action_set.update(action_list)
    predicate_set = set()
    for predicate in pred2category.keys():
        predicate_set.add(predicate)

    # load evaluation dict
    gold_action_dict = json.load(open(gold_action_path, "r"))
    

    # logical score (precison, recall, f1)
    # 1. precond logical score based on type 
    # 2. effect logical score based on type 
    # 3. precond logical score per action (fig)
    # 4. effect logical score per action (fig)
    # potentially record score for each predicate

    precond_predicate_type_res_dict = {}
    effect_predicate_type_res_dict = {}
    full_predicate_type_res_dict = {}
    precond_action_type_dict = {}
    effect_action_type_dict = {}
    full_action_type_dict = {}

    precond_predicate_score_dict = {}
    effect_predicate_score_dict = {}
    full_predicate_score_dict = {}
    
    # 5. success rate by planner on task type
    success_by_task_type_dict = {}

    # sensitivity analysis
    # 6. action success rate by planner on task type (precond, effect) -- change all operators/precond/effect by predicted in task
    task_variate_control_by_type = {} # all
    task_variate_control_precond_by_type = {} # precond
    task_variate_control_effect_by_type = {} # effect
    # 7. action success rate by planner for all action (precond, effect)
    action_variate_control = {} # all
    action_variate_control_precond = {} # precond
    action_variate_control_effect = {} # effect

    for category_type in categories_set:
        # [success(TP), precond false positive fail(FP), missing fail(FN)]
        precond_predicate_type_res_dict[category_type] = [0, 0, 0]
        effect_predicate_type_res_dict[category_type] = [0, 0, 0]
        success_by_task_type_dict[category_type] = [0, 0] # [success, total]
        task_variate_control_by_type[category_type] = {}
        task_variate_control_precond_by_type[category_type] = {}
        task_variate_control_effect_by_type[category_type] = {}

    # micro avg
    for action in action_set:
        # [success(TP), precond false positive fail(FP), missing fail(FN)]
        precond_action_type_dict[action] = [0, 0, 0]
        effect_action_type_dict[action] = [0, 0, 0]
        action_variate_control[action] = [0, 0] # [success, total]
        action_variate_control_precond[action] = [0, 0] # [success, total]
        action_variate_control_effect[action] = [0, 0] # [success, total]

    for pred in predicate_set:
        precond_predicate_score_dict[pred] = [0, 0, 0]
        effect_predicate_score_dict[pred] = [0, 0, 0]

    # macro avg
    # for action in action_set:
    #     operator_score_dict[action] = [0.0, 0.0, 0]  # [precond, effect, total]

    planner = FD()
    total_num = 0
    format_wrong_num = 0

    print("start evaluation")
    # print(f'{task_dict=}')
    # predicate_vocabulary = json.loads(open(vocabulary_path, 'r').open())
    for output_dict in helm_output:
        file_id = output_dict["identifier"]
        if file_id not in success_file_id:
            continue

        total_num += 1

        task_name = id2task[file_id]
        print(f"task name is {task_name}")
        # if task_name not in ["Turn on light"]:
        #     continue
        
        task_name = "_".join(task_name.split())
        task_problem_dir = os.path.join(pddl_problem_dir, task_name)
        problem_path = os.path.join(task_problem_dir, f"{file_id}.pddl")
        
        category_name_list = id2category[file_id]
        print(f"category names are {category_name_list}")

        predicted_action = output_dict["llm_output"]
        try:
            predicted_action = json.loads(predicted_action)
            predicted_action = predicted_action["output"]
        except Exception as e:
            try:
                predicted_action = parse_json(predicted_action)
                if predicted_action is None:
                    format_wrong_num += 1
                    print(f"format wrong num is {format_wrong_num}")
                else:
                    predicted_action = predicted_action["output"]
            except Exception as e:
                format_wrong_num += 1
                print(f"format wrong num is {format_wrong_num}")
        # print(predicted_action, flush=True)
        if predicted_action is None or predicted_action == "":
            continue
        predicted_action = extract_action_details(content=predicted_action)
        print("GPT predicted action body:", flush=True)

        predicted_domain_path = os.path.join(pddl_root, f"predicted_{model_name}")
        gold_domain_path = os.path.join(pddl_root, f"gold_{model_name}")
        os.makedirs(predicted_domain_path, exist_ok=True)
        os.makedirs(gold_domain_path, exist_ok=True)

        gold_actions = {}
        gold_actions_name = id2action[file_id]
        for action_name in gold_actions_name:
            gold_actions[action_name] = gold_action_dict[action_name]

        # start eval
        for action_name, action_dict in predicted_action.items():
            if action_name not in gold_action_dict.keys():
                continue
            
            gold_action = gold_actions[action_name]

            # print predicted action
            pred_str = ""
            pred_str += f":action {action_name}\n"
            pred_str += f'  :parameters {action_dict["action_parameters"]}\n'
            pred_str += f'  :preconditions {action_dict["action_preconditions"]}\n'
            pred_str += f'  :effects {action_dict["action_effects"]}\n'

            gold_str = ""
            gold_str += f":action {action_name}\n"
            gold_str += f'  :parameters {gold_action["action_parameters"]}\n'
            gold_str += f'  :preconditions {gold_action["action_preconditions"]}\n'
            gold_str += f'  :effects {gold_action["action_effects"]}\n'

            print("Gold action:")
            special_print(gold_str)
            print("GPT predicted action")
            special_print(pred_str)

            # logical score
            gold_action = gold_action_dict[action_name]

            # match preconditions and effects
            (
                precond_similarity_score,
                matched_precond,
                unmatched_pred_precond,
                unmatched_gold_precond,
            ) = calculate_logic_score(
                action_dict["action_preconditions"],
                gold_action["action_preconditions"],
            )
            (
                effect_similarity_score,
                matched_effect,
                unmatched_pred_effect,
                unmatched_gold_effect,
            ) = calculate_logic_score(
                action_dict["action_effects"], gold_action["action_effects"]
            )


            # record precondition
            for pred in matched_precond:
                if pred == "()":
                    continue
                precond_predicate_type_res_dict[pred2category[pred]][0] += 1
                precond_action_type_dict[action_name][0] += 1
                precond_predicate_score_dict[pred][0] += 1
            print(f"{unmatched_pred_precond=}")
            for pred in unmatched_pred_precond:
                if pred == "()":
                    continue
                if pred not in pred2category.keys():
                    continue
                precond_predicate_type_res_dict[pred2category[pred]][1] += 1
                precond_action_type_dict[action_name][1] += 1
                precond_predicate_score_dict[pred][1] += 1
            for pred in unmatched_gold_precond:
                if pred == "()":
                    continue
                precond_predicate_type_res_dict[pred2category[pred]][2] += 1
                precond_action_type_dict[action_name][2] += 1
                precond_predicate_score_dict[pred][2] += 1
            
            # record effect
            for pred in matched_effect:
                if pred == "()":
                    continue
                effect_predicate_type_res_dict[pred2category[pred]][0] += 1
                effect_action_type_dict[action_name][0] += 1
                effect_predicate_score_dict[pred][0] += 1
            for pred in unmatched_pred_effect:
                if pred == "()":
                    continue
                if pred not in pred2category.keys():
                    continue
                effect_predicate_type_res_dict[pred2category[pred]][1] += 1
                effect_action_type_dict[action_name][1] += 1
                effect_predicate_score_dict[pred][1] += 1
            for pred in unmatched_gold_effect:
                if pred == "()":
                    continue
                effect_predicate_type_res_dict[pred2category[pred]][2] += 1
                effect_action_type_dict[action_name][2] += 1
                effect_predicate_score_dict[pred][2] += 1


        predicted_action_copy = copy.deepcopy(predicted_action)
        # success rate by planner & sensitivity analysis
        # partial operator trials
        # category_name_list = id2category[file_id]

        # increase tot number for success rate
        for category_name in category_name_list:
            success_by_task_type_dict[category_name][1] += 1
            # increase tot number for sensitivity analysis
            for action in gold_actions_name:
                if action not in task_variate_control_by_type[category_name].keys():
                    task_variate_control_by_type[category_name][action] = [0, 1]
                else:
                    task_variate_control_by_type[category_name][action][1] += 1
                if action not in task_variate_control_precond_by_type[category_name]:
                    task_variate_control_precond_by_type[category_name][action] = [0, 1]
                else:
                    task_variate_control_precond_by_type[category_name][action][1] += 1
                if action not in task_variate_control_effect_by_type[category_name]:
                    task_variate_control_effect_by_type[category_name][action] = [0, 1]
                else:
                    task_variate_control_effect_by_type[category_name][action][1] += 1
                
                action_variate_control[action][1] += 1
                action_variate_control_precond[action][1] += 1
                action_variate_control_effect[action][1] += 1
        
        # gold action trial
        for action_name in predicted_action.keys():
            assert predicted_action_copy == predicted_action
            if action_name not in gold_action_dict.keys():
                print(f"{action_name} not in gold")
                continue
            single_variate_action = {}
            gold_action_dict_copy = copy.deepcopy(gold_action_dict)
            for gd_action_name in gold_actions_name:
                single_variate_action[gd_action_name] = copy.deepcopy(
                    gold_action_dict_copy[gd_action_name]
                )
            domain_file_path = complete_pddl_domain(
                single_variate_action,
                gold_action_dict,
                domain_pd_path,
                file_id,
                predicted_domain_path,
                action_name_key='gold',
            )
            try:
                pddl_plan = planner.plan_from_pddl(domain_file_path, problem_path)
                print(f"{pddl_plan=}")
                print(f"Gold test: task {file_id}'s {action_name} succeeded")
            except Exception as e:
                raise e
                print(f"Gold test: task {file_id}'s {action_name} failed")

        # per action trial
        for action_name in predicted_action.keys():
            assert predicted_action_copy == predicted_action
            if action_name not in gold_action_dict.keys():
                print(f"{action_name} not in gold")
                continue
            single_variate_action = {}
            gold_action_dict_copy = copy.deepcopy(gold_action_dict)
            for gd_action_name in gold_actions_name:
                single_variate_action[gd_action_name] = copy.deepcopy(gold_action_dict_copy[gd_action_name])
            single_variate_action[action_name] = copy.deepcopy(predicted_action_copy[action_name])
            # print(f"{single_variate_action=}")
            domain_file_path = complete_pddl_domain(
                single_variate_action,
                gold_action_dict,
                domain_pd_path,
                file_id,
                predicted_domain_path,
                action_name_key=action_name,
            )
            try:
                pddl_plan = planner.plan_from_pddl(domain_file_path, problem_path)
                for category_name in category_name_list:
                    task_variate_control_by_type[category_name][action_name][0] += 1
                action_variate_control[action_name][0] += 1
                print(f"Action test: task {file_id}'s {action_name} succeeded")
            except Exception as e:
                print(f"Action test: task {file_id}'s {action_name} failed")

        # precondition / effect trial
        for action_name in predicted_action.keys():
            assert predicted_action_copy == predicted_action
            if action_name not in gold_action_dict.keys():
                print(f"{action_name} not in gold")
                continue
            single_variate_action = {}
            gold_action_dict_copy = copy.deepcopy(gold_action_dict)
            for gd_action_name in gold_actions_name:
                single_variate_action[gd_action_name] = copy.deepcopy(gold_action_dict_copy[
                    gd_action_name
                ])
            single_variate_action[action_name]["action_preconditions"] = copy.deepcopy(
                predicted_action_copy[action_name]["action_preconditions"]
            )
            domain_file_path = complete_pddl_domain(
                single_variate_action,
                gold_action_dict,
                domain_pd_path,
                file_id,
                predicted_domain_path,
                action_name_key=action_name + "_precond",
            )
            try:
                pddl_plan = planner.plan_from_pddl(domain_file_path, problem_path)
                for category_name in category_name_list:
                    task_variate_control_precond_by_type[category_name][action_name][0] += 1
                action_variate_control_precond[action_name][0] += 1
                print(f"Precondition test: task {file_id}'s {action_name} succeeded")
            except Exception as e:
                print(f"Precondition test: task {file_id}'s {action_name} failed")

        for action_name in predicted_action.keys():
            assert predicted_action_copy == predicted_action
            if action_name not in gold_action_dict.keys():
                print(f"{action_name} not in gold")
                continue
            single_variate_action = {}
            gold_action_dict_copy = copy.deepcopy(gold_action_dict)
            for gd_action_name in gold_actions_name:
                single_variate_action[gd_action_name] = (
                    copy.deepcopy(gold_action_dict_copy[gd_action_name]
                ))
            single_variate_action[action_name]["action_effects"] = copy.deepcopy(
                predicted_action_copy[action_name]["action_effects"]
            )
            domain_file_path = complete_pddl_domain(
                single_variate_action,
                gold_action_dict,
                domain_pd_path,
                file_id,
                predicted_domain_path,
                action_name_key=action_name + "_effect",
            )
            try:
                pddl_plan = planner.plan_from_pddl(domain_file_path, problem_path)
                for category_name in category_name_list:
                    task_variate_control_effect_by_type[category_name][action_name][0] += 1
                action_variate_control_effect[action_name][0] += 1
                print(f"Effect test: task {file_id}'s {action_name} succeeded")
            except Exception as e:
                print(f"Effect test: task {file_id}'s {action_name} failed")

        # all action trial
        domain_file_path = complete_pddl_domain(
            predicted_action,
            gold_action_dict,
            domain_pd_path,
            file_id,
            predicted_domain_path,
        )
        try:
            pddl_plan = planner.plan_from_pddl(domain_file_path, problem_path)
            for category_name in category_name_list:
                success_by_task_type_dict[category_name][0] += 1
            print(f"Holistic test: task {file_id} succeeded")
        except Exception as e:
            print(f"Holistic test: task {file_id} failed")

        # single action ablation
        # ablation_action = "walk_towards"
        # if ablation_action not in task_ablation_dict.keys():
        #     task_ablation_dict[ablation_action] = {}
        # if task_name not in task_ablation_dict[ablation_action].keys():
        #     task_ablation_dict[ablation_action][task_name] = [0, 1]
        # else:
        #     task_ablation_dict[ablation_action][task_name][1] += 1
        # print(f"Ablation on {ablation_action}!")
        # walk_ablation = predicted_action_copy
        # walk_ablation[ablation_action] = gold_action_dict[ablation_action]
        # domain_file_path = complete_pddl_domain(
        #     walk_ablation,
        #     gold_action_dict,
        #     domain_pd_path,
        #     file_id,
        #     predicted_domain_path,
        #     action_name_key=ablation_action + "_ablation",
        # )
        # try:
        #     pddl_plan = planner.plan_from_pddl(domain_file_path, problem_path)
        #     task_ablation_dict[ablation_action][task_name][0] += 1
        #     print(f"Ablation test: task {file_id} succeeded")
        # except:
        #     print(f"Ablation test: task {file_id} failed")

        sys.stdout.flush()


    # results post-processing logical scores

    # full is the sum of precond and effect
    for category_type in categories_set:
        full_predicate_type_res_dict[category_type] = [
            precond_predicate_type_res_dict[category_type][0]
            + effect_predicate_type_res_dict[category_type][0],
            precond_predicate_type_res_dict[category_type][1]
            + effect_predicate_type_res_dict[category_type][1],
            precond_predicate_type_res_dict[category_type][2]
            + effect_predicate_type_res_dict[category_type][2],
        ]
    
    # full is the sum of precond and effect
    for action in action_set:
        full_action_type_dict[action] = [
            precond_action_type_dict[action][0] + effect_action_type_dict[action][0],
            precond_action_type_dict[action][1] + effect_action_type_dict[action][1],
            precond_action_type_dict[action][2] + effect_action_type_dict[action][2],
        ]
    
    # full is the sum of precond and effect
    for pred in predicate_set:
        full_predicate_score_dict[pred] = [
            precond_predicate_score_dict[pred][0] + effect_predicate_score_dict[pred][0],
            precond_predicate_score_dict[pred][1] + effect_predicate_score_dict[pred][1],
            precond_predicate_score_dict[pred][2] + effect_predicate_score_dict[pred][2],
        ]

    # precond logical score based on type
    precond_predicate_type_res_dict = calculate_precision_recall_f1(
        precond_predicate_type_res_dict
    )

    # effect logical score based on type
    effect_predicate_type_res_dict = calculate_precision_recall_f1(
        effect_predicate_type_res_dict
    )

    full_predicate_type_res_dict = calculate_precision_recall_f1(full_predicate_type_res_dict)

    # precond logical score per action
    precond_action_type_dict = calculate_precision_recall_f1(precond_action_type_dict)

    # effect logical score per action
    effect_action_type_dict = calculate_precision_recall_f1(effect_action_type_dict)

    full_action_type_dict = calculate_precision_recall_f1(full_action_type_dict)
    
    # precondition predicate score per predicate
    precond_predicate_score_dict = calculate_precision_recall_f1(precond_predicate_score_dict)

    # effect predicate score per predicate
    effect_predicate_score_dict = calculate_precision_recall_f1(effect_predicate_score_dict)

    # full predicate score per predicate
    full_predicate_score_dict = calculate_precision_recall_f1(full_predicate_score_dict)

    print(f'Format wrong num is {format_wrong_num}!!!')

    # post-process success rate by planner on task type
    success_by_task_type_dict = calculate_success_rate(success_by_task_type_dict)
    print("Success by task type dict:")
    print_success_rate(success_by_task_type_dict)

    # print out precision recall f1 
    print("Precondition predicate type res dict:")
    print_precision_recall_f1(precond_predicate_type_res_dict)
    print("Effect predicate type res dict:")
    print_precision_recall_f1(effect_predicate_type_res_dict)
    print("Full predicate type res dict:")
    print_precision_recall_f1(full_predicate_type_res_dict)
    print("Precondition action type dict:")
    print_precision_recall_f1(precond_action_type_dict)
    print("Effect action type dict:")
    print_precision_recall_f1(effect_action_type_dict)
    print("Full action type dict:")
    print_precision_recall_f1(full_action_type_dict)
    print("Precondition predicate score dict:")
    print_precision_recall_f1(precond_predicate_score_dict)
    print("Effect predicate score dict:")
    print_precision_recall_f1(effect_predicate_score_dict)
    print("Full predicate score dict:")
    print_precision_recall_f1(full_predicate_score_dict)


    # post-process sensitivity analysis
    task_variate_control_by_type = calculate_success_rate_by_category(task_variate_control_by_type)
    task_variate_control_precond_by_type = calculate_success_rate_by_category(
        task_variate_control_precond_by_type
    )
    task_variate_control_effect_by_type = calculate_success_rate_by_category(
        task_variate_control_effect_by_type
    )

    print("Task variate control by type:")
    print_success_rate_by_category(task_variate_control_by_type)
    print("Task variate control precond by type:")
    print_success_rate_by_category(task_variate_control_precond_by_type)
    print("Task variate control effect by type:")
    print_success_rate_by_category(task_variate_control_effect_by_type)
    print("Action variate control:")
    print(action_variate_control)
    print("Action variate control precond:")
    print(action_variate_control_precond)
    print("Action variate control effect:")
    print(action_variate_control_effect)

    # save results
    if save_results:
        json.dump(precond_predicate_type_res_dict, open(precond_predicate_type_res_dict_path, "w"), indent=4)
        json.dump(effect_predicate_type_res_dict, open(effect_predicate_type_res_dict_path, "w"), indent=4)
        json.dump(full_predicate_type_res_dict, open(full_predicate_type_res_dict_path, "w"), indent=4)
        json.dump(precond_action_type_dict, open(precond_action_type_dict_path, "w"), indent=4)
        json.dump(effect_action_type_dict, open(effect_action_type_dict_path, "w"), indent=4)
        json.dump(full_action_type_dict, open(full_action_type_dict_path, "w"), indent=4)
        json.dump(precond_predicate_score_dict, open(precond_predicate_res_dict_path, "w"), indent=4)
        json.dump(effect_predicate_score_dict, open(effect_predicate_res_dict_path, "w"), indent=4)
        json.dump(full_predicate_score_dict, open(full_predicate_res_dict_path, "w"), indent=4)
        json.dump(
            success_by_task_type_dict, open(success_by_task_type_dict_path, "w"), indent=4
        )
        json.dump(task_variate_control_by_type, open(task_variate_control_by_type_path, "w"), indent=4)
        json.dump(task_variate_control_precond_by_type, open(task_variate_control_precond_by_type_path, "w"), indent=4)
        json.dump(task_variate_control_effect_by_type, open(task_variate_control_effect_by_type_path, "w"), indent=4)
        json.dump(action_variate_control, open(action_variate_control_path, "w"), indent=4)
        json.dump(action_variate_control_precond, open(action_variate_control_precond_path, "w"), indent=4)
        json.dump(action_variate_control_effect, open(action_variate_control_effect_path, "w"), indent=4)
    
    

    


    # path_args = {
    #     "precond_predicate_type_res_dict_path": precond_predicate_type_res_dict_path,
    #     "precond_predicate_res_dict_path": precond_predicate_res_dict_path,
    #     "effect_predicate_type_res_dict_path": effect_predicate_type_res_dict_path,
    #     "effect_predicate_res_dict_path": effect_predicate_res_dict_path,
    #     "full_predicate_type_res_dict_path": full_predicate_type_res_dict_path,
    #     "full_predicate_res_dict_path": full_predicate_res_dict_path,
    #     "precond_predicate_type_res_fig_path": precond_predicate_type_res_fig_path,
    #     "precond_predicate_res_fig_path": precond_predicate_res_fig_path,
    #     "effect_predicate_type_res_fig_path": effect_predicate_type_res_fig_path,
    #     "effect_predicate_res_fig_path": effect_predicate_res_fig_path,
    #     "full_predicate_type_res_fig_path": full_predicate_type_res_fig_path,
    #     "full_predicate_res_fig_path": full_predicate_res_fig_path,
    # }

    # visualization
    if visualization:
        operator_visualization(**path_args)
    return


def task_categorization():
    k = 2
    # per_task_res_path = os.path.join(save_root, 'per_task_res.json')
    # full_predicate_type_res_dict_path = os.path.join(save_root, 'full_predicate_type_res_dict.json')
    resource_root = (
        "/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/virtualhome"
    )
    gold_action_path = osp.join(resource_root, "gold_action.json")
    id2action_path = osp.join(resource_root, "id2action.json")
    pred_category_path = osp.join(resource_root, "predicates_category.json")

    gold_action_dict = json.load(open(gold_action_path, "r"))
    id2action = json.load(open(id2action_path, "r"))
    predicate_categories = json.load(open(pred_category_path, "r"))

    id_to_task_path = os.path.join(resource_root, "id2task.json")
    id2predicate_path = os.path.join(resource_root, "id2predicate.json")
    gold_action_w_pred_path = os.path.join(resource_root, "gold_action_w_pred.json")
    id2category_path = os.path.join(resource_root, f"id2category_{k}.json")
    task_category_cnt_path = os.path.join(resource_root, f"task_category_cnt_{k}.json")
    category2id_path = os.path.join(resource_root, f"category2id_{k}.json")

    if os.path.exists(id_to_task_path):
        id_to_task = json.load(open(id_to_task_path, "r"))
    else:
        id_to_task = {}
        task_dict_dir = "/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/task_state_updated.json"
        task_dict = json.load(open(task_dict_dir, "r"))
        scene_1_dict = task_dict["scene_1"]
        for task_name, task_details in scene_1_dict.items():
            t_ids = task_details["task_file_list_with_ans"]
            goal_id_to_task = group_by_index(t_ids)
            for id_list in goal_id_to_task.values():
                for idx in id_list:
                    id_to_task[idx] = task_name
        json.dump(id_to_task, open(id_to_task_path, "w"), indent=4)

    if os.path.exists(gold_action_w_pred_path):
        gold_action_dict = json.load(open(gold_action_w_pred_path, "r"))
    else:
        for action_name, action_dict in gold_action_dict.items():
            pred_set = set()
            action_preconditions = action_dict["action_preconditions"]
            action_effects = action_dict["action_effects"]
            score, matched, unmatched_pred, unmatched_gold = calculate_logic_score(
                action_preconditions, action_preconditions
            )
            print(f"{score=}, {matched=}, {unmatched_pred=}, {unmatched_gold=}")
            assert (
                score == 1.0 and len(unmatched_pred) == 0 and len(unmatched_gold) == 0
            )
            pred_set.update(matched)
            score, matched, unmatched_pred, unmatched_gold = calculate_logic_score(
                action_effects, action_effects
            )
            print(f"{score=}, {matched=}, {unmatched_pred=}, {unmatched_gold=}")
            assert (
                score == 1.0 and len(unmatched_pred) == 0 and len(unmatched_gold) == 0
            )
            pred_set.update(matched)
            if "()" in pred_set:
                pred_set.remove("()")
            gold_action_dict[action_name]["pred_set"] = list(pred_set)

        json.dump(gold_action_dict, open(gold_action_w_pred_path, "w"), indent=4)

    if os.path.exists(id2predicate_path):
        id2predicates = json.load(open(id2predicate_path, "r"))
    else:
        id2predicates = {}
        for id, action_list in id2action.items():
            pred_list = []
            for action_name in action_list:
                if action_name not in gold_action_dict.keys():
                    print(f"{action_name} not in gold!!! Double check!!!")
                    continue
                pred_set = gold_action_dict[action_name]["pred_set"]
                pred_list.extend(pred_set)
            id2predicates[id] = pred_list
        json.dump(id2predicates, open(id2predicate_path, "w"), indent=4)

    # calculate IDF
    pred_frequency = defaultdict(int)
    for id, pred_list in id2predicates.items():
        seen_predicates = set()
        for predicate in pred_list:
            if predicate == "()":
                continue
            if predicate not in seen_predicates:
                pred_frequency[predicate] += 1
                seen_predicates.add(predicate)

    total_docs = len(id2predicates)
    idf_scores = {
        predicate: math.log(total_docs / df) for predicate, df in pred_frequency.items()
    }

    print(f"{idf_scores=}")
    print("\n")

    # Score programs based on categories
    program_scores = {}
    for id, pred_list in id2predicates.items():
        category_scores = defaultdict(float)
        for predicate in pred_list:
            if predicate == "()":
                continue
            category = predicate_categories[predicate]
            category_scores[category] += idf_scores[predicate]
        program_scores[id] = category_scores

    # print(f"{program_scores=}")
    # print("\n")

    # Categorize each program
    program_categories = {}

    for id, category_scores in program_scores.items():
        # take the top k categories
        topk_categories = sorted(
            category_scores, key=category_scores.get, reverse=True
        )[:k]
        program_categories[id] = topk_categories

    program_category_cnt = {}
    for category_lst in program_categories.values():
        for category in category_lst:
            if category not in program_category_cnt:
                program_category_cnt[category] = 0
            program_category_cnt[category] += 1

    category2program = defaultdict(list)
    for id, category_lst in program_categories.items():
        for category in category_lst:
            category2program[category].append(id)

    print(f"{program_categories=}")
    print("\n")
    print(f"{program_category_cnt=}")
    print("\n")

    json.dump(program_categories, open(id2category_path, "w"), indent=4)
    json.dump(program_category_cnt, open(task_category_cnt_path, "w"), indent=4)
    json.dump(category2program, open(category2id_path, "w"), indent=4)


def operator_visualization(**kwargs):
    precond_predicate_type_res_dict = json.loads(
        open(kwargs["precond_predicate_type_res_dict_path"], "r").read()
    )
    precond_predicate_res_dict = json.loads(
        open(kwargs["precond_predicate_res_dict_path"], "r").read()
    )
    effect_predicate_type_res_dict = json.loads(
        open(kwargs["effect_predicate_type_res_dict_path"], "r").read()
    )
    effect_predicate_res_dict = json.loads(
        open(kwargs["effect_predicate_res_dict_path"], "r").read()
    )
    full_predicate_type_res_dict = json.loads(
        open(kwargs["full_predicate_type_res_dict_path"], "r").read()
    )
    full_predicate_res_dict = json.loads(
        open(kwargs["full_predicate_res_dict_path"], "r").read()
    )

    operator_score_dict = json.loads(
        open(kwargs["operator_score_dict_path"], "r").read()
    )

    error_draw_chart(
        precond_predicate_type_res_dict, kwargs["precond_predicate_type_res_fig_path"]
    )
    error_draw_chart(
        precond_predicate_res_dict,
        kwargs["precond_predicate_res_fig_path"],
        rotation=45,
        divide_k=3,
    )
    error_draw_chart(
        effect_predicate_type_res_dict, kwargs["effect_predicate_type_res_fig_path"]
    )
    error_draw_chart(
        effect_predicate_res_dict,
        kwargs["effect_predicate_res_fig_path"],
        rotation=45,
        divide_k=3,
    )
    error_draw_chart(
        full_predicate_type_res_dict, kwargs["full_predicate_type_res_fig_path"]
    )
    error_draw_chart(
        full_predicate_res_dict,
        kwargs["full_predicate_res_fig_path"],
        rotation=45,
        divide_k=3,
    )

    draw_bar_chart(operator_score_dict, kwargs["operator_score_fig_path"], divide_k=3)


def pddl_problem_construction():
    properties_data = utils.load_properties_data()
    object_placing = utils.load_object_placing()
    name_equivalence = utils.load_name_equivalence()
    data_path = "/viscam/u/shiyuz/virtualhome/virtualhome/dataset/programs_processed_precond_nograb_morepreconds/init_and_final_graphs/TrimmedTestScene1_graph/results_intentions_march-13-18"
    domain_path = "/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/pddl_files/virtualhome.pddl"
    task_dict_dir = "/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/task_state_updated.json"
    pddl_problem_dir = "/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/pddl_files/virtualhome"

    task_dict = json.load(open(task_dict_dir, "r"))
    scene_str = "scene_1"
    task_dict = task_dict[scene_str]
    # predicate_vocabulary = json.loads(open(vocabulary_path, 'r').open())
    for task_name, task_detail in task_dict.items():
        # if task_name in ['Wash dishes by hand', 'Write an email', 'Wash hands']:
        #     continue
        if task_name != "Pet cat":
            continue
        task_name = "_".join(task_name.split())
        task_problem_dir = os.path.join(pddl_problem_dir, task_name)
        if not os.path.exists(task_problem_dir):
            os.makedirs(task_problem_dir)
        print(f"task name is {task_name}")
        task_list = task_detail["task_file_list"]
        task_list_ans_list = task_detail["task_file_list_with_ans"]
        goal_candidates = task_detail["goal_candidates"]
        for file_id in task_list:
            if file_id != "115_2":
                continue
            # we first get candidate num
            ans_id = get_candidate_id(file_id, task_list_ans_list)
            if ans_id == -1:
                continue
            goal = goal_candidates[ans_id]

            problem_dir = os.path.join(task_problem_dir, f"{file_id}.pddl")
            state_file_path = os.path.join(data_path, f"file{file_id}.json")
            state_dict = json.load(open(state_file_path, "r"))
            init_state_dict = state_dict["init_graph"]
            final_state_dict = state_dict["final_graph"]

            init_scene_graph = EnvironmentGraph(init_state_dict)
            planner = MotionPlanner(
                init_scene_graph,
                final_state_dict,
                name_equivalence,
                properties_data,
                object_placing,
            )

            relevant_nodes, related_ids = get_relevant_nodes(planner)

            initial_states, goal_states, actions_states, name2id = (
                get_initial_states_and_final_goals_wo_id(planner, goal, relevant_nodes)
            )

            pddl_file = create_pddl_problem(
                domain_path, initial_states, goal_states, relevant_nodes, task_name
            )

            # save pddl_file
            with open(problem_dir, "w") as f:
                f.write(pddl_file)
            # print(f'{object_in_scene=}')
            print(f"{relevant_nodes=}")
            print(f"{related_ids=}")
            print(f"{initial_states=}")
            print(f"{goal_states=}")
            print(f"{actions_states=}")
            print(f"{name2id=}")
            print(f"{pddl_file=}")
    return


def construct_behavior_pddl():
    dataset = "virtualhome"
    resource_root = (
        f"/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/{dataset}"
    )

    pddl_problem_dir = osp.join(resource_root, "problem_pddl")
    os.makedirs(pddl_problem_dir, exist_ok=True)

    problem_pddl_list = json.load(open(problem_pddl, "r"))
    for pd_dict in problem_pddl_list:
        identifier = pd_dict["identifier"]
        problem_pddl = pd_dict["problem_pddl"]
        problem_pddl_path = osp.join(pddl_problem_dir, f"{identifier}.pddl")
        with open(problem_pddl_path, "w") as f:
            special_write(problem_pddl, f)


def evaluate_pddl_planner():
    dataset = "virtualhome"
    resource_root = (
        f"/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/{dataset}"
    )

    pddl_root = osp.join(resource_root, "pddl_files")
    pddl_problem_dir = osp.join(resource_root, "problem_pddl")
    os.makedirs(pddl_root, exist_ok=True)
    os.makedirs(pddl_problem_dir, exist_ok=True)

    domain_path = osp.join(resource_root, f"{dataset}.pddl")

    success_dict_path = osp.join(resource_root, "success_task.json")
    fail_dict_path = osp.join(resource_root, "failed_task.json")
    id2action_path = osp.join(resource_root, "id2action.json")
    gold_pddl_plan_path = osp.join(resource_root, "gold_pddl_plan.json")

    planner = FD()
    failed_list = []
    successed_list = []
    id2action = {}
    gold_pddl_plan_dict = {}
    save_flag = True

    # search through all files in pddl_problem_dir
    for task_name in os.listdir(pddl_problem_dir):
        # remove .pddl in each filename
        print(f"Current task is {task_name}")
        if task_name in ["Wash_dishes_by_hand", "Write_an_email", "Wash_hands"]:
            continue
        for file_name in os.listdir(osp.join(pddl_problem_dir, task_name)):
            if not file_name.endswith(".pddl"):
                continue
            identifier = file_name.split(".")[0]
            problem_path = osp.join(pddl_problem_dir, task_name, file_name)
            print(f"Task identifier is {identifier}")
            try:
                # print(f'{cmd_str=}')
                pddl_plan = planner.plan_from_pddl(domain_path, problem_path)
                print(f"{pddl_plan=}")
                gold_action_list = []
                for act in pddl_plan:
                    action = act.split()[0]
                    gold_action_list.append(action)
                id2action[identifier] = list(set(gold_action_list))
                gold_pddl_plan_dict[identifier] = pddl_plan
                successed_list.append(identifier)
                print("Test passed")
            except Exception as e:
                failed_list.append(identifier)
                print(f"An error occurred: {e}")

    if save_flag:
        with open(fail_dict_path, "w") as f:
            json.dump(failed_list, f)
        with open(id2action_path, "w") as f:
            json.dump(id2action, f)
        with open(success_dict_path, "w") as f:
            json.dump(successed_list, f)
        with open(gold_pddl_plan_path, "w") as f:
            json.dump(gold_pddl_plan_dict, f)
    print(f"{failed_list=}")
    return


def planner_test():
    domain_file_path = "/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/virtualhome/pddl_files/predicted_gpt-4o/11_1_gold.pddl"
    problem_path = "/viscam/u/shiyuz/svl_project/AgentEval/virtualhome/resources/virtualhome/pddl_files/virtualhome/Turn_on_light/11_1.pddl"
    planner = FD()
    plan = planner.plan_from_pddl(domain_file_path, problem_path)
    print(f"{plan=}")