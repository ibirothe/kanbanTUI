from rich.console import Console
from rich.table import Table


def split_items(data):
    todos = []
    inprogs = []
    dones = []

    for key, value in data["data"].items():
        if value[0] == "todo":
            todos.append("[%d] %s" % (key, value[1]))
        elif value[0] == "inprogress":
            inprogs.append("[%d] %s" % (key, value[1]))
        else:
            dones.insert(0, "[%d] %s" % (key, value[1]))

    return todos, inprogs, dones


def render_board(config, data, version: str) -> None:
    todos, inprogs, dones = split_items(data)
    dones = dones[: config["limits"]["done"]]

    table = Table(show_header=True, show_footer=True)
    table.add_column(
        "[bold yellow]todo[/bold yellow]", no_wrap=True, footer="clikan"
    )
    table.add_column("[bold green]in-progress[/bold green]", no_wrap=True)
    table.add_column(
        "[bold magenta]done[/bold magenta]",
        no_wrap=True,
        footer=f"v.{version}",
    )
    table.add_row("\n".join(todos), "\n".join(inprogs), "\n".join(dones))
    Console().print(table)
