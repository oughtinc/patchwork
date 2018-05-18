import cmd

from typing import Optional

from .datastore import Datastore
from .scheduling import Action, Scheduler, Context, AskSubquestion, Reply, Unlock, Scratch

class UserInterface(cmd.Cmd):
    intro = "What is your root question?"
    prompt = "> "

    def __init__(self, db: Datastore, scheduler: Scheduler) -> None:
        super().__init__()
        self.db = db
        self.scheduler = scheduler
        self.current_context: Optional[Context] = None

    def precmd(self, line: str) -> str:
        print("---")
        return line

    def default(self, line: str) -> bool:
        if self.current_context is None:
            self.scheduler.ask_root_question(line)
            self.current_context = self.scheduler.choose_context()
            return False
        else:
            return super().default(line)

    def emptyline(self) -> bool:
        return False

    def postcmd(self, stop: bool, line: str) -> bool:
        self.prompt = "{}\n{}".format(str(self.current_context), UserInterface.prompt)
        return stop

    def _do(self, action: Action) -> None:
        if self.current_context is None:
            raise ValueError("trying to do an action without a current context")
        self.scheduler.resolve_action(self.current_context, action)
        self.current_context = self.scheduler.choose_context()

    def do_ask(self, arg: str) -> bool:
        self._do(AskSubquestion(arg))
        return False

    def do_reply(self, arg: str) -> bool:
        self._do(Reply(arg))
        return False

    def do_unlock(self, arg: str) -> bool:
        self._do(Unlock(arg))
        return False

    def do_scratch(self, arg: str) -> bool:
        self._do(Scratch(arg))
        return False


