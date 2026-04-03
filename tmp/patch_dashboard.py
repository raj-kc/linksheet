import os
import re

views_path = r'c:\Users\kumar\Desktop\LinkSheet\sheets\views.py'
with open(views_path, 'r', encoding='utf-8') as f:
    views_content = f.read()

# 1. Fix dashboard view by restoring joined_sheets
target = '''    context = {
        "created_sheets": my_sheets,  # unified list for "My Sheets" tab
        "joined_sheets": [],          # Keep empty to maintain compatibility if anything expects it
        "total_sheets": len(my_sheets),
        "total_rows": total_rows,
        "last_activity": last_act,
    }'''

replacement = '''    joined_members = (
        SheetMember.objects
        .select_related("sheet", "sheet__owner")
        .filter(user=user, is_active=True, sheet__is_active=True)
        .exclude(role='collaborator')
        .exclude(sheet__owner=user)
    )
    
    context = {
        "created_sheets": my_sheets,
        "joined_sheets": [m.sheet for m in joined_members],
        "total_sheets": len(my_sheets) + joined_members.count(),
        "total_rows": total_rows,
        "last_activity": last_act,
    }'''

if target in views_content:
    views_content = views_content.replace(target, replacement)
    with open(views_path, 'w', encoding='utf-8') as f:
        f.write(views_content)


db_path = r'c:\Users\kumar\Desktop\LinkSheet\templates\dashboard.html'
with open(db_path, 'r', encoding='utf-8') as f:
    db_content = f.read()

# 2. Convert manage modal to unified modal
add_form_html = """            <!-- Combined Add Collaborator Form -->
            <div class="mb-5 bg-blue-50/50 p-4 rounded-xl border border-blue-100">
                <form id="manageAddCollabForm" class="flex flex-col gap-2">
                    <input type="hidden" id="manageCollabSheetId">
                    <label class="block text-[13px] font-bold text-blue-900">Invite a Collaborator</label>
                    <div class="flex items-center gap-2">
                        <input type="email" id="manageCollabEmail" required placeholder="colleague@example.com" class="flex-1 px-3 py-2 bg-white border border-blue-200 rounded-lg text-sm focus:border-blue-400 focus:ring-2 focus:ring-blue-100 outline-none transition-all">
                        <button type="submit" id="btnManageAddCollab" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-bold text-sm transition-colors flex items-center gap-2 shadow-sm whitespace-nowrap">
                            Add
                        </button>
                    </div>
                </form>
            </div>
            
            <div class="border-t border-gray-100 mt-2 pt-4">
                <h4 class="text-[13px] font-bold text-gray-700 mb-3">Current Collaborators</h4>
"""

# inject form right inside <div class="p-6"> of the Remove Collaborator Modal
if 'manageAddCollabForm' not in db_content:
    db_content = re.sub(
        r'(<div id="removeCollaboratorModal".*?<div class="p-6">)',
        r'\1\n' + add_form_html,
        db_content,
        flags=re.DOTALL
    )


# Update JS `openRemoveCollaboratorModal` to populate `manageCollabSheetId`
js_target = "const listContainer = document.getElementById('manageCollabListContainer');"
js_replacement = """        document.getElementById('manageCollabSheetId').value = sheetId;
        const listContainer = document.getElementById('manageCollabListContainer');"""
if 'manageCollabSheetId' not in db_content:
    db_content = db_content.replace(js_target, js_replacement)

# JS Logic for adding
add_logic_js = """
    document.getElementById('manageAddCollabForm')?.addEventListener('submit', async function(e) {
        e.preventDefault();
        const sheetId = document.getElementById('manageCollabSheetId').value;
        const emailInput = document.getElementById('manageCollabEmail');
        const email = emailInput.value;
        const btn = document.getElementById('btnManageAddCollab');
        const errorDiv = document.getElementById('remCollabError');
        
        btn.innerHTML = '<i class="ph-bold ph-spinner animate-spin"></i>';
        btn.disabled = true;
        errorDiv.classList.add('hidden');
        errorDiv.classList.remove('flex');
        
        try {
            const response = await fetch(`/api/sheets/${sheetId}/collaborators/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ email: email })
            });
            const data = await response.json();
            
            if (response.ok) {
                // Hard reload to refresh HTML members list
                window.location.reload();
            } else {
                document.getElementById('remCollabErrorMsg').innerText = data.error || 'Failed to add collaborator';
                errorDiv.classList.remove('hidden');
                errorDiv.classList.add('flex');
                btn.innerHTML = 'Add';
                btn.disabled = false;
            }
        } catch(err) {
            document.getElementById('remCollabErrorMsg').innerText = 'Network error occurred';
            errorDiv.classList.remove('hidden');
            errorDiv.classList.add('flex');
            btn.innerHTML = 'Add';
            btn.disabled = false;
        }
    });
"""

script_end_target = "// === DOWNLOAD MENU TOGGLE ==="
if 'manageAddCollabForm' not in db_content.split('// === DOWNLOAD MENU TOGGLE')[0]:
    db_content = db_content.replace(script_end_target, add_logic_js + '\n' + script_end_target)


# 3. Remove standalone Add Collaborator UI completely
db_content = re.sub(
    r'<!-- Add Collaborator button -->.*?<button onclick="openAddCollaboratorModal[^>]*?>.*?</button>',
    '',
    db_content,
    flags=re.DOTALL
)

db_content = re.sub(
    r'<!-- Add Collaborator Modal -->.*?<div id="removeCollaboratorModal"',
    '<div id="removeCollaboratorModal"',
    db_content,
    flags=re.DOTALL
)

db_content = re.sub(
    r'// Add Collaborator Logic.*?function closeAddCollaboratorModal\(\) \{.*?(?:return cookieValue;\s*\}\s*)?document\.getElementById\(\'addCollaboratorForm\'\).*?\}\);',
    '',
    db_content,
    flags=re.DOTALL
)

with open(db_path, 'w', encoding='utf-8') as f:
    f.write(db_content)
