from langgraph.graph import END, START, StateGraph

from app.agents.api_specialist import execute_api_node
from app.agents.evaluator import evaluate_node
from app.agents.supervisor import plan_tests_node, validate_inputs_node
from app.agents.ui_specialist import execute_ui_node
from app.models import RunState
from app.reports.reporter import report_node


def route_after_validation(state: RunState) -> str:
    if state.get("run_phase") == "PLANNING":
        return "plan_tests"
    return END


def route_after_planning(state: RunState) -> str:
    if state.get("run_phase") == "EXECUTING":
        return "execute_api"
    return END


def create_testing_graph():
    builder = StateGraph(RunState)

    builder.add_node("validate_inputs", validate_inputs_node)
    builder.add_node("plan_tests", plan_tests_node)
    builder.add_node("execute_api", execute_api_node)
    builder.add_node("execute_ui", execute_ui_node)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("report", report_node)

    builder.add_edge(START, "validate_inputs")
    builder.add_conditional_edges("validate_inputs", route_after_validation)
    builder.add_conditional_edges("plan_tests", route_after_planning)
    builder.add_edge("execute_api", "execute_ui")
    builder.add_edge("execute_ui", "evaluate")
    builder.add_edge("evaluate", "report")
    builder.add_edge("report", END)

    return builder.compile()


graph = create_testing_graph()
