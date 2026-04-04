from django.http import JsonResponse
from sheets.models import SheetSyncEvent

def debug_errors(request):
    errors = SheetSyncEvent.objects.exclude(error='').exclude(error__isnull=True).values('action', 'error', 'created_at', 'processed')
    return JsonResponse({'errors': list(errors)})
