import datetime

from .models import AppConfig, Board, Task, TaskState


def timestamp() -> str:
    return "{:%Y-%b-%d %H:%M:%S}".format(datetime.datetime.now())


def _count_state(board: Board, state: TaskState) -> int:
    return sum(1 for task in board.active.values() if task.state is state)


def wip_limit_reached(config: AppConfig, board: Board) -> bool:
    if config.limits.wip is None:
        return False
    return config.limits.wip <= _count_state(board, TaskState.IN_PROGRESS)


def add_tasks(config: AppConfig, board: Board, tasks):
    messages = []

    for text in tasks:
        if len(text) > config.limits.taskname:
            messages.append(
                "Task must be at most %s chars, Brevity counts: %s"
                % (config.limits.taskname, text)
            )
            continue

        if (
            config.limits.todo is not None
            and config.limits.todo <= _count_state(board, TaskState.TODO)
        ):
            messages.append("No new todos, limit reached already.")
            continue

        task_id = max(board.active, default=0) + 1
        now = timestamp()
        board.active[task_id] = Task(
            id=task_id,
            state=TaskState.TODO,
            text=text,
            modified_at=now,
            created_at=now,
        )
        messages.append("Creating new task w/ id: %d -> %s" % (task_id, text))

    return messages


def delete_tasks(board: Board, ids):
    messages = []
    for task_id in ids:
        try:
            numeric_id = int(task_id)
        except ValueError:
            messages.append("Invalid task id")
            continue

        task = board.active.get(numeric_id)
        if task is None:
            messages.append("No existing task with that id: %d" % numeric_id)
            continue

        task.state = TaskState.DELETED
        task.modified_at = timestamp()
        board.deleted[numeric_id] = task
        board.active.pop(numeric_id)
        messages.append("Removed task %d." % numeric_id)

    return messages


def promote_tasks(config: AppConfig, board: Board, ids):
    messages = []
    for task_id in ids:
        try:
            numeric_id = int(task_id)
        except ValueError:
            messages.append("Invalid task id")
            continue

        task = board.active.get(numeric_id)
        if task is None:
            messages.append("No existing task with that id: %s" % task_id)
        elif task.state is TaskState.TODO:
            if wip_limit_reached(config, board):
                messages.append(
                    "Can not promote, in-progress limit of %s reached."
                    % config.limits.wip
                )
            else:
                task.state = TaskState.IN_PROGRESS
                task.modified_at = timestamp()
                messages.append("Promoting task %s to in-progress." % task_id)
        elif task.state is TaskState.IN_PROGRESS:
            task.state = TaskState.DONE
            task.modified_at = timestamp()
            messages.append("Promoting task %s to done." % task_id)
        else:
            messages.append("Can not promote %s, already done." % task_id)

    return messages


def regress_tasks(config: AppConfig, board: Board, ids):
    messages = []
    for task_id in ids:
        try:
            numeric_id = int(task_id)
        except ValueError:
            messages.append("Invalid task id")
            continue

        task = board.active.get(numeric_id)
        if task is None:
            messages.append("No existing task with id: %s" % task_id)
        elif task.state is TaskState.DONE:
            if wip_limit_reached(config, board):
                messages.append(
                    "Can not regress, in-progress limit of %s reached."
                    % config.limits.wip
                )
            else:
                task.state = TaskState.IN_PROGRESS
                task.modified_at = timestamp()
                messages.append("Regressing task %s to in-progress." % task_id)
        elif task.state is TaskState.IN_PROGRESS:
            task.state = TaskState.TODO
            task.modified_at = timestamp()
            messages.append("Regressing task %s to todo." % task_id)
        else:
            messages.append("Already in todo, can not regress %s" % task_id)

    return messages
