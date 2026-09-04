from kanban_tui.services import add_tasks, delete_tasks, promote_tasks, regress_tasks


def base_config(**limits):
    return {
        "clikan_data": "/tmp/unused",
        "limits": {"taskname": 40, "done": 10, **limits},
        "repaint": False,
    }


def empty_board():
    return {"data": {}, "deleted": {}}


def test_add_and_delete_tasks():
    data = empty_board()

    add_messages = add_tasks(base_config(), data, ["one", "two"])
    delete_messages = delete_tasks(data, ["1"])

    assert len(data["data"]) == 1
    assert 1 in data["deleted"]
    assert "Creating new task w/ id: 1 -> one" in add_messages
    assert "Removed task 1." in delete_messages


def test_batch_promotion_respects_wip_limit():
    data = empty_board()
    config = base_config(wip=1)
    add_tasks(config, data, ["one", "two"])

    messages = promote_tasks(config, data, ["1", "2"])

    assert data["data"][1][0] == "inprogress"
    assert data["data"][2][0] == "todo"
    assert "Can not promote, in-progress limit of 1 reached." in messages


def test_regress_done_respects_wip_limit():
    data = {
        "data": {
            1: ["inprogress", "one", "now", "before"],
            2: ["done", "two", "now", "before"],
        },
        "deleted": {},
    }
    config = base_config(wip=1)

    messages = regress_tasks(config, data, ["2"])

    assert data["data"][2][0] == "done"
    assert "Can not regress, in-progress limit of 1 reached." in messages


def test_regress_inprogress_returns_to_todo():
    data = {
        "data": {1: ["inprogress", "one", "now", "before"]},
        "deleted": {},
    }

    messages = regress_tasks(base_config(), data, ["1"])

    assert data["data"][1][0] == "todo"
    assert "Regressing task 1 to todo." in messages
