import datetime


def timestamp() -> str:
    return "{:%Y-%b-%d %H:%M:%S}".format(datetime.datetime.now())


def _count_state(data, state: str) -> int:
    return sum(1 for item in data["data"].values() if item[0] == state)


def wip_limit_reached(config, data) -> bool:
    if "wip" not in config["limits"]:
        return False
    return config["limits"]["wip"] <= _count_state(data, "inprogress")


def add_tasks(config, data, tasks):
    messages = []
    taskname_length = config["limits"]["taskname"]

    for task in tasks:
        if len(task) > taskname_length:
            messages.append(
                "Task must be at most %s chars, Brevity counts: %s"
                % (taskname_length, task)
            )
            continue

        if (
            "todo" in config["limits"]
            and config["limits"]["todo"] <= _count_state(data, "todo")
        ):
            messages.append("No new todos, limit reached already.")
            continue

        new_id = max(data["data"], default=0) + 1
        data["data"][new_id] = ["todo", task, timestamp(), timestamp()]
        messages.append("Creating new task w/ id: %d -> %s" % (new_id, task))

    return messages


def delete_tasks(data, ids):
    messages = []
    for task_id in ids:
        try:
            numeric_id = int(task_id)
        except ValueError:
            messages.append("Invalid task id")
            continue

        item = data["data"].get(numeric_id)
        if item is None:
            messages.append("No existing task with that id: %d" % numeric_id)
            continue

        item[0] = "deleted"
        item[2] = timestamp()
        data["deleted"][numeric_id] = item
        data["data"].pop(numeric_id)
        messages.append("Removed task %d." % numeric_id)

    return messages


def promote_tasks(config, data, ids):
    messages = []
    for task_id in ids:
        try:
            numeric_id = int(task_id)
        except ValueError:
            messages.append("Invalid task id")
            continue

        item = data["data"].get(numeric_id)
        if item is None:
            messages.append("No existing task with that id: %s" % task_id)
        elif item[0] == "todo":
            if wip_limit_reached(config, data):
                messages.append(
                    "Can not promote, in-progress limit of %s reached."
                    % config["limits"]["wip"]
                )
            else:
                data["data"][numeric_id] = [
                    "inprogress",
                    item[1],
                    timestamp(),
                    item[3],
                ]
                messages.append("Promoting task %s to in-progress." % task_id)
        elif item[0] == "inprogress":
            data["data"][numeric_id] = [
                "done",
                item[1],
                timestamp(),
                item[3],
            ]
            messages.append("Promoting task %s to done." % task_id)
        else:
            messages.append("Can not promote %s, already done." % task_id)

    return messages


def regress_tasks(config, data, ids):
    messages = []
    for task_id in ids:
        try:
            numeric_id = int(task_id)
        except ValueError:
            messages.append("Invalid task id")
            continue

        item = data["data"].get(numeric_id)
        if item is None:
            messages.append("No existing task with id: %s" % task_id)
        elif item[0] == "done":
            if wip_limit_reached(config, data):
                messages.append(
                    "Can not regress, in-progress limit of %s reached."
                    % config["limits"]["wip"]
                )
            else:
                data["data"][numeric_id] = [
                    "inprogress",
                    item[1],
                    timestamp(),
                    item[3],
                ]
                messages.append("Regressing task %s to in-progress." % task_id)
        elif item[0] == "inprogress":
            data["data"][numeric_id] = [
                "todo",
                item[1],
                timestamp(),
                item[3],
            ]
            messages.append("Regressing task %s to todo." % task_id)
        else:
            messages.append("Already in todo, can not regress %s" % task_id)

    return messages
