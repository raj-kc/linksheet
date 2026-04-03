
    function openRemoveCollaboratorModal(sheetId, btnElem) {
        let collabsText = btnElem.getAttribute('data-collabs');
        collabsText = collabsText.replace(/,\s*\]$/, ']'); 
        let collabs = [];
        try { 
            collabs = JSON.parse(collabsText); 
        } catch(e) { 
            console.error(e);
            collabs = []; 
        }
        
        const mSheetIdInput = document.getElementById('manageCollabSheetId');
        if (mSheetIdInput) mSheetIdInput.value = sheetId;

        const listContainer = document.getElementById('manageCollabListContainer');
        if (!listContainer) return;
        listContainer.innerHTML = '';
        
        collabs = collabs.filter(c => c && c.email);
        
        if(collabs.length === 0) {
            listContainer.innerHTML = '<p class="text-sm text-gray-400 text-center py-4 font-semibold">No active collaborators found.</p>';
        } else {
            collabs.forEach(c => {
                const div = document.createElement('div');
                div.className = "flex items-center justify-between p-3 border border-gray-100 rounded-lg bg-gray-50 shadow-sm transition-all hover:bg-white";
                div.innerHTML = `
                    <div class="flex items-center gap-3">
                        <div class="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-xs uppercase">
                            ${c.username.substring(0,2)}
                        </div>
                        <div>
                            <p class="font-bold text-gray-800 text-[13px] leading-tight">${c.username}</p>
                            <p class="text-gray-500 text-[11px] mt-0.5">${c.email}</p>
                        </div>
                    </div>
                    <button type="button" class="text-gray-400 hover:text-red-600 hover:bg-red-50 w-8 h-8 flex items-center justify-center rounded-md transition-colors rem-btn" title="Remove">
                        <i class="ph-bold ph-trash text-lg"></i>
                    </button>
                `;
                div.querySelector('.rem-btn').onclick = () => removeCollabReq(sheetId, c.email, div.querySelector('.rem-btn'));
                listContainer.appendChild(div);
            });
        }
        
        const errDiv = document.getElementById('remCollabError');
        if (errDiv) {
            errDiv.classList.add('hidden');
            errDiv.classList.remove('flex');
        }

        const modal = document.getElementById('removeCollaboratorModal');
        if (!modal) return;
        modal.classList.remove('hidden');
        setTimeout(() => {
            modal.classList.remove('opacity-0');
            modal.querySelector('.transform').classList.remove('scale-95');
        }, 10);
    }
    
    function closeRemoveCollaboratorModal() {
        const modal = document.getElementById('removeCollaboratorModal');
        if (!modal) return;
        modal.classList.add('opacity-0');
        modal.querySelector('.transform').classList.add('scale-95');
        setTimeout(() => {
            modal.classList.add('hidden');
        }, 300);
    }

    async function removeCollabReq(sheetId, email, btnElem) {
        if(!confirm(`Remove ${email} from collaborators? They will lose write access to the Google Sheet.`)) return;
        
        const errorDiv = document.getElementById('remCollabError');
        const errorMsg = document.getElementById('remCollabErrorMsg');
        
        const originalHtml = btnElem.innerHTML;
        btnElem.innerHTML = '<i class="ph-bold ph-spinner animate-spin text-lg text-emerald-500"></i>';
        btnElem.disabled = true;
        
        try {
            const response = await fetch(`/api/sheets/${sheetId}/collaborators/remove/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({ email: email })
            });
            const data = await response.json();
            
            if (response.ok) {
                const row = btnElem.closest('div.flex');
                row.style.opacity = '0';
                row.style.transform = 'scale(0.95)';
                setTimeout(() => {
                    row.remove();
                    const listContainer = document.getElementById('manageCollabListContainer');
                    if(listContainer && listContainer.children.length === 0) {
                        listContainer.innerHTML = '<p class="text-sm text-gray-400 text-center py-4 font-semibold">No active collaborators found.</p>';
                    }
                }, 300);
            } else {
                if (errorMsg) errorMsg.innerText = data.error || 'Failed to remove';
                if (errorDiv) {
                    errorDiv.classList.remove('hidden');
                    errorDiv.classList.add('flex');
                }
                btnElem.innerHTML = originalHtml;
                btnElem.disabled = false;
            }
        } catch(e) {
            if (errorMsg) errorMsg.innerText = 'Network Error';
            if (errorDiv) {
                errorDiv.classList.remove('hidden');
                errorDiv.classList.add('flex');
            }
            btnElem.innerHTML = originalHtml;
            btnElem.disabled = false;
        }
    }

    // Initialize Add form
    window.addEventListener('DOMContentLoaded', () => {
        const addForm = document.getElementById('manageAddCollabForm');
        if (addForm) {
            addForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                const sheetId = document.getElementById('manageCollabSheetId').value;
                const emailInput = document.getElementById('manageCollabEmail');
                const btn = document.getElementById('btnManageAddCollab');
                const errorDiv = document.getElementById('remCollabError');
                const errorMsg = document.getElementById('remCollabErrorMsg');
                
                const email = emailInput.value;
                btn.innerHTML = '<i class="ph-bold ph-spinner animate-spin"></i>';
                btn.disabled = true;
                if (errorDiv) errorDiv.classList.add('hidden');
                
                try {
                    const response = await fetch(`/api/sheets/${sheetId}/collaborators/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCSRFToken()
                        },
                        body: JSON.stringify({ email: email })
                    });
                    const data = await response.json();
                    
                    if (response.ok) {
                        window.location.reload();
                    } else {
                        if (errorMsg) errorMsg.innerText = data.error || 'Failed to add';
                        if (errorDiv) {
                            errorDiv.classList.remove('hidden');
                            errorDiv.classList.add('flex');
                        }
                        btn.innerHTML = 'Add';
                        btn.disabled = false;
                    }
                } catch(err) {
                    if (errorMsg) errorMsg.innerText = 'Network error occurred';
                    if (errorDiv) {
                        errorDiv.classList.remove('hidden');
                        errorDiv.classList.add('flex');
                    }
                    btn.innerHTML = 'Add';
                    btn.disabled = false;
                }
            });
        }
    });



function switchTab(tabName) {
        const tabs = ['created', 'joined'];
        
        tabs.forEach(t => {
            const content = document.getElementById(`tab-${t}`);
            const btn = document.getElementById(`btn-${t}`);
            if (!content || !btn) return;
            
            if (t === tabName) {
                content.classList.remove('hidden');
                setTimeout(() => content.classList.remove('opacity-0'), 10);
                
                btn.classList.add('border-gray-900', 'text-gray-900', 'font-semibold');
                btn.classList.remove('border-transparent', 'text-gray-400', 'font-normal');
            } else {
                content.classList.add('opacity-0');
                setTimeout(() => content.classList.add('hidden'), 300);
                
                btn.classList.remove('border-gray-900', 'text-gray-900', 'font-semibold');
                btn.classList.add('border-transparent', 'text-gray-400', 'font-normal');
            }
        });
    }
