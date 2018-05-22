"""Basic Functional HCH"""

import pickle
import sys

from .datastore import Datastore
from .scheduling import RootQuestionSession, Scheduler
from .interface import UserInterface


def main(argv):
    if len(argv) > 1:
        try:
            with open(argv[1], 'rb') as f:
                db, sched = pickle.load(f)
        except FileNotFoundError:
            db = Datastore()
            sched = Scheduler(db)
    else:
        db = Datastore()
        sched = Scheduler(db)
    print("What is your root question?")
    with RootQuestionSession(sched, input("> ")) as sess:
        ui = UserInterface(sess)
        ui.cmdloop()

    if len(argv) > 1:
        with open(argv[1], "wb") as f:
            pickle.dump((db, sched), f)

if __name__ == "__main__":
    main(sys.argv)

