class OperationCancelled(Exception):
    pass


def check_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelled("Vorgang wurde abgebrochen.")
