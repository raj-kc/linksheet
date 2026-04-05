from django.http import JsonResponse
from sheets.models import SheetSyncEvent

def debug_errors(request):
    errors = SheetSyncEvent.objects.exclude(error='').exclude(error__isnull=True).values('action', 'error', 'created_at', 'processed')
    pending = SheetSyncEvent.objects.filter(processed=False).values('action', 'created_at')
    total = SheetSyncEvent.objects.count()
    return JsonResponse({'errors': list(errors), 'pending': list(pending), 'total': total})
