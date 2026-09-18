import traceback
from backend.orchestrator.supervisor import Supervisor

try:
    result = Supervisor().handle_with_metadata('test', 'Draft an Outlook email to the customer')
    print(result)
except Exception:
    traceback.print_exc()
