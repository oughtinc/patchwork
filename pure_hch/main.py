"""Basic Functional HCH"""

import sys

from .datastore import Datastore
from .scheduling import RootQuestionSession, Scheduler
from .interface import UserInterface


def main(argv):
    db = Datastore()
    print("What is your root question?")
    sched = Scheduler(db)
    with RootQuestionSession(sched, input("> ")) as sess:
        ui = UserInterface(sess)
        ui.cmdloop()

if __name__ == "__main__":
    main(sys.argv)

