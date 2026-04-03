

function switchTab(tabName) {
    const tabs = ['created', 'joined'];
    
    tabs.forEach(t => {
        const content = document.getElementById(`tab-${t}`);
        const btn = document.getElementById(`btn-${t}`);
        
        if (t === tabName) {
            // Show logic
            content.classList.remove('hidden');
            // Small delay to allow display:block to apply before changing opacity for transition
            setTimeout(() => content.classList.remove('opacity-0'), 10);
            
            // Button Styles
            btn.classList.add('border-primary', 'text-primary');
            btn.classList.remove('border-transparent', 'text-muted');
        } else {
            // Hide logic
            content.classList.add('opacity-0');
            setTimeout(() => content.classList.add('hidden'), 300); // Wait for transition
            
            // Button Styles
            btn.classList.remove('border-primary', 'text-primary');
            btn.classList.add('border-transparent', 'text-muted');
        }
    });
}

let isRefreshing = false; // Prevent multiple refresh calls

// === CORE MODAL FUNCTIONS ===
function openModal(modalId, initData = null) {
    const modal = document.getElementById(modalId);
    if (!modal) {
        console.error(`Modal ${modalId} not found`);
        return;
    }

    const backdrop = modal.querySelector('.modal-backdrop');
    const panel = modal.querySelector('.modal-panel');

    if (initData && modalId === 'shareSheetModal') {
        initializeShareModal(initData);
    }

    modal.classList.remove("hidden");
    
    setTimeout(() => {
        if (backdrop) backdrop.classList.remove("opacity-0");
        if (panel) {
            panel.classList.remove("opacity-0", "scale-95");
            panel.classList.add("opacity-100", "scale-100");
        }
    }, 10);
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;

    const backdrop = modal.querySelector('.modal-backdrop');
    const panel = modal.querySelector('.modal-panel');

    // Animate out
    if (backdrop) backdrop.classList.add("opacity-0");
    if (panel) {
        panel.classList.remove("opacity-100", "scale-100");
        panel.classList.add("opacity-0", "scale-95");
    }

    // Hide & refresh after animation
    setTimeout(() => {
        modal.classList.add("hidden");
        resetModal(modalId);
        
        // 🚀 AUTO-REFRESH CREATED SHEETS TABLE
        if (modalId === 'shareSheetModal') {
            refreshCreatedSheetsTable();
        }
    }, 300);
}

// === REFRESH FUNCTION - Updates table without page reload ===
async function refreshCreatedSheetsTable() {
    if (isRefreshing) return; // Prevent duplicate calls
    
    isRefreshing = true;
    
    try {
        const response = await fetch('/sheets/created/', { // Your endpoint to get created sheets
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
            }
        });

        if (response.ok) {
            const sheetsData = await response.json();
            updateSheetsTable(sheetsData);
        }
    } catch (error) {
        console.error('Refresh failed:', error);
    } finally {
        isRefreshing = false;
    }
}

// === UPDATE TABLE WITH NEW DATA ===
function updateSheetsTable(sheetsData) {
    const tbody = document.querySelector('#tab-created tbody');
    if (!tbody || !sheetsData || !sheetsData.sheets) return;

    if (sheetsData.sheets.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="px-6 py-12 text-center">
                    <div class="flex flex-col items-center justify-center text-muted">
                        <i class="ph-duotone ph-folder-dashed text-4xl mb-3 opacity-50"></i>
                        <p class="font-medium">No sheets created yet</p>
                        <p class="text-xs mt-1">Create your first sheet to get started</p>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    // Build new rows
    const rows = sheetsData.sheets.map(sheet => `
        <tr class="hover:bg-gray-50/80 transition-colors group">
            <td class="px-6 py-4 font-medium text-foreground flex items-center gap-3">
                <div class="p-2 bg-green-100 text-green-700 rounded-md">
                    <i class="ph-fill ph-file-xls"></i>
                </div>
                ${escapeHtml(sheet.name)}
            </td>
            <td class="px-6 py-4 text-muted">${sheet.created_at}</td>
            <td class="px-6 py-4">
                <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200">
                    <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span> Live
                </span>
            </td>
            <td class="px-6 py-4 text-muted font-medium">${sheet.response_count}</td>
            <td class="px-6 py-4 text-right">
                <div class="flex items-center justify-end gap-2 opacity-60 group-hover:opacity-100 transition-opacity">
                    <a href="${sheet.google_url}" target="_blank" title="View in Google Sheets" 
                    class="p-2 rounded-md hover:bg-green-50 text-muted hover:text-green-600 transition-colors">
                        <i class="ph-bold ph-google-logo"></i>
                    </a>
                    <button onclick="copySheetLink('${sheet.share_link}')" title="Copy Share Link"
                            class="p-2 rounded-md hover:bg-purple-50 text-muted hover:text-purple-600 transition-colors">
                        <i class="ph-bold ph-link"></i>
                    </button>
                    <div class="relative download-dropdown">
                        <button onclick="toggleDownloadMenu(event, '${sheet.id}')"
                                id="download-btn-${sheet.id}"
                                title="Download"
                                class="p-2 rounded-md hover:bg-blue-50 text-muted hover:text-blue-600 transition-colors">
                            
                            <i class="ph-bold ph-download-simple" id="download-icon-${sheet.id}"></i>
                            <i class="ph-bold ph-spinner animate-spin text-lg hidden" id="download-spinner-${sheet.id}"></i>
                        </button>

                        <div id="download-menu-${sheet.id}" class="hidden absolute right-0 mt-2 w-40 bg-white rounded-lg shadow-lg border border-gray-200 z-10">
                            <a href="#" onclick="handleDownload(event, '${sheet.id}', 'xlsx')" class="block px-4 py-2 text-sm hover:bg-gray-50 rounded-t-lg">
                                <i class="ph-bold ph-file-xls mr-2"></i>Excel (.xlsx)
                            </a>
                            <a href="#" onclick="handleDownload(event, '${sheet.id}', 'csv')" class="block px-4 py-2 text-sm hover:bg-gray-50 rounded-b-lg">
                                <i class="ph-bold ph-file-csv mr-2"></i>CSV (.csv)
                            </a>
                        </div>
                    </div>
                    <button onclick="confirmDeleteSheet('${sheet.id}', '${escapeHtml(sheet.name)}')" title="Delete Sheet"
                            class="p-2 rounded-md hover:bg-red-50 text-muted hover:text-red-600 transition-colors">
                        <i class="ph-bold ph-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');

    tbody.innerHTML = rows;
}

// === HTML ESCAPE for security ===
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// === MODAL SPECIFIC ===
function initializeShareModal(data) {
    document.getElementById("shareLinkInput").value = data.share_link;
    document.getElementById("openSheetBtn").href = data.sheet_url;
}

function resetModal(modalId) {
    if (modalId === 'createSheetModal') {
        const form = document.getElementById("createSheetForm");
        const btn = document.getElementById("btn-create-submit");
        if (form) form.reset();
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<span>Create Sheet</span><i class="ph-bold ph-arrow-right"></i>`;
        }
    } else if (modalId === 'shareSheetModal') {
        document.getElementById("shareLinkInput").value = "";
    } else if (modalId === 'joinSheetModal') {
        const jsForm = document.getElementById("joinSheetForm");
        const jsBtn = document.getElementById("btn-join-submit");
        if(jsForm) jsForm.reset();
        if(jsBtn) {
            jsBtn.disabled = false;
            jsBtn.innerHTML = `Join Sheet <i class="ph-bold ph-arrow-right"></i>`;
        }
    }
}

function copyShareLink() {
    const input = document.getElementById("shareLinkInput");
    input.select();
    document.execCommand("copy");
    
    // Show feedback & auto-refresh
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = 'Copied!';
    btn.classList.add('bg-green-600');
    
    setTimeout(() => {
        closeModal("shareSheetModal");
    }, 800);
}

function copySheetLink(button) {
    const shareLink = button.dataset.shareLink;

    if (!shareLink) {
        console.error('Share link missing');
        showToast('Share link not available', 'error');
        return;
    }

    copyToClipboard(shareLink);
}

function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text)
            .then(() => showToast('Share link copied!', 'success'))
            .catch(() => fallbackCopy(text));
    } else {
        fallbackCopy(text);
    }
}


// === DOWNLOAD MENU TOGGLE ===
function toggleDownloadMenu(event, sheetId) {
    event.stopPropagation();

    const menu = document.getElementById(`download-menu-${sheetId}`);

    if (!menu) {
        console.error(`Download menu not found for sheetId: ${sheetId}`);
        return;
    }

    menu.classList.toggle('hidden');
}

// Close dropdown when clicking outside
document.addEventListener('click', function() {
    document.querySelectorAll('[id^="download-menu-"]').forEach(m => m.classList.add('hidden'));
});

// === HANDLE DOWNLOAD CLICKS ===
function handleDownload(event, sheetId, format) {
    event.preventDefault();

    const icon = document.getElementById(`download-icon-${sheetId}`);
    const spinner = document.getElementById(`download-spinner-${sheetId}`);
    const menu = document.getElementById(`download-menu-${sheetId}`);

    // 1️⃣ Show spinner, hide icon
    icon.classList.add('hidden');
    spinner.classList.remove('hidden');

    // 2️⃣ Trigger download
    const downloadUrl = `/sheets/${sheetId}/download/?format=${format}`;
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = '';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // 3️⃣ Close dropdown
    menu.classList.add('hidden');

    // 4️⃣ Hide spinner & show success toast (after download starts)
    setTimeout(() => {
        spinner.classList.add('hidden');
        icon.classList.remove('hidden');

        showToast(
            `Sheet downloaded successfully as ${format.toUpperCase()}`,
            'success'
        );
    }, 800); // slight delay feels natural
}



// === DELETE SHEET ===
async function confirmDeleteSheet(sheetId, sheetName) {
    if (!confirm(`Are you sure you want to delete "${sheetName}"? This action cannot be undone.`)) {
        return;
    }

    try {
        const response = await fetch(`/sheets/${sheetId}/delete/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken()
            }
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showToast('Sheet deleted successfully', 'success');
            refreshCreatedSheetsTable();
        } else {
            showToast(data.error || 'Failed to delete sheet', 'error');
        }
    } catch (error) {
        console.error('Delete failed:', error);
        showToast('An error occurred', 'error');
    }
}


function getCSRFToken() {
    const name = 'csrftoken=';
    const cookies = document.cookie.split(';');

    for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.startsWith(name)) {
            return cookie.substring(name.length);
        }
    }
    return '';
}



// === TOAST NOTIFICATION ===
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `fixed bottom-4 right-4 px-6 py-3 rounded-lg shadow-lg text-white z-50 ${
        type === 'success' ? 'bg-green-600' : 'bg-red-600'
    }`;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}


// === FORM HANDLER ===
document.addEventListener('DOMContentLoaded', function() {
    
    // Create Sheet Handler
    const createForm = document.getElementById("createSheetForm");
    if(createForm) {
        createForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            const btn = document.getElementById("btn-create-submit");
            const originalContent = btn.innerHTML;

            btn.disabled = true;
            btn.innerHTML = `<i class="ph-bold ph-spinner animate-spin text-lg"></i> Creating...`;

            const formData = new FormData(this);

            try {
                const response = await fetch("/create-sheet/", {
                    method: "POST",
                    headers: { "X-CSRFToken": getCSRFToken() },
                    body: formData
                });

                if (response.ok) {
                    const data = await response.json();
                    closeModal('createSheetModal');
                    openModal('shareSheetModal', data);
                } else {
                    alert("Failed to create sheet. Please check your connection and try again.");
                }
            } catch (error) {
                alert("Failed to create sheet. Please try again.");
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalContent;
            }
        });
    }

    // Join Sheet Handler (extracting token from pasted URL)
    const joinForm = document.getElementById("joinSheetForm");
    if(joinForm) {
        joinForm.addEventListener("submit", function(e) {
            e.preventDefault();
            const urlInput = document.getElementById("joinSheetUrl").value.trim();
            if(!urlInput) return;
            
            let token = urlInput;
            if(token.includes('/join/')) {
                const parts = token.split('/join/');
                if(parts.length > 1) {
                    token = parts[1].split('/')[0];
                }
            }
            // Strip trailing/leading slashes just in case
            token = token.replace(/^\/+|\/+$/g, '');
            
            const btn = document.getElementById("btn-join-submit");
            btn.innerHTML = `<i class="ph-bold ph-spinner animate-spin text-lg"></i> Joining...`;
            btn.disabled = true;
            
            // Redirect to the regular Join route
            window.location.href = "/join/" + token + "/";
        });
    }
});

document.addEventListener('keydown', function(event) {
    if (event.key === "Escape") {
        const openModals = document.querySelectorAll('.modal-wrapper:not(.hidden)');
        if (openModals.length > 0) {
            closeModal(openModals[0].id);
        }
    }
});





// --- State Management ---
let currentSheetId = null;
let currentData = { columns: [], rows: [] };
let editingRowIndex = null; // null = create mode, number = edit mode

let editingRowId = null;

let lastTempId = null;
const gridBody = document.getElementById("grid-body");
const gridHeader = document.getElementById("grid-header-row");



// --- 1. Modal Open/Close ---

function openDataGrid(sheetId) {
    currentSheetId = sheetId;
    const modal = document.getElementById("dataGridModal");
    const backdrop = document.getElementById("gridBackdrop");
    const panel = document.getElementById("gridPanel");

    modal.classList.remove("hidden");
    
    // Animate In
    setTimeout(() => {
        backdrop.classList.remove("opacity-0");
        panel.classList.remove("opacity-0", "scale-95");
        panel.classList.add("opacity-100", "scale-100");
    }, 10);

    fetchGridData();
}

function closeDataGrid() {
    const modal = document.getElementById("dataGridModal");
    const backdrop = document.getElementById("gridBackdrop");
    const panel = document.getElementById("gridPanel");

    // Animate Out
    backdrop.classList.add("opacity-0");
    panel.classList.remove("opacity-100", "scale-100");
    panel.classList.add("opacity-0", "scale-95");

    setTimeout(() => {
        modal.classList.add("hidden");
        closeDrawer(); // Ensure drawer is closed
        document.getElementById("grid-body").innerHTML = ""; // Clean up
    }, 300);
}

// --- 2. Data Fetching ---
    
function fetchGridData() {
    const loader = document.getElementById("grid-loader");
    const emptyState = document.getElementById("grid-empty");

    loader.classList.remove("hidden");
    emptyState.classList.add("hidden");

    fetch(`/api/sheets/${currentSheetId}/grid/`)
        .then(res => {
            if (!res.ok) throw new Error("Failed to fetch grid data");
            return res.json();
        })
        .then(data => {
            // 🔥 State is the ONLY thing updated here
            currentData = {
                title: data.title,
                columns: data.columns || [],
                rows: data.rows || []
            };

            // Title
            document.getElementById("grid-title").innerText =
                currentData.title || "Untitled Sheet";

            // 🔁 Single render pipeline
            renderTable();
        })
        .catch(err => {
            console.error(err);
            showToast("Failed to load records", "error");
        })
        .finally(() => {
            loader.classList.add("hidden");
        });
}



// --- 3. Render Table Dynamically ---

function renderTable() {
    const theadRow = document.getElementById("grid-header-row");
    const tbody = document.getElementById("grid-body");
    const emptyState = document.getElementById("grid-empty");

    theadRow.innerHTML = "";
    tbody.innerHTML = "";

    if (!currentData.rows || currentData.rows.length === 0) {
        emptyState.classList.remove("hidden");
        return;
    }

    emptyState.classList.add("hidden");

    // ---------- HEADERS ----------
    currentData.columns.forEach(col => {
        const th = document.createElement("th");
        th.className =
            "px-6 py-3 text-xs font-semibold text-muted uppercase tracking-wider " +
            "bg-gray-50/80 sticky top-0 whitespace-nowrap border-b border-border";
        th.innerText = col;
        theadRow.appendChild(th);
    });

    const thAction = document.createElement("th");
    thAction.className =
        "px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider " +
        "text-right sticky top-0 bg-gray-50/80 border-b border-border w-[140px]";
    thAction.innerText = "Actions";
    theadRow.appendChild(thAction);

    // ---------- ROWS ----------
    currentData.rows.forEach((row, index) => {
        const tr = document.createElement("tr");
        tr.className =
            "group hover:bg-gray-50/70 transition-colors";

        currentData.columns.forEach(col => {
            const td = document.createElement("td");
            td.className =
                "px-6 py-4 text-sm text-gray-700 whitespace-nowrap " +
                "border-b border-border";
            td.innerText = row.data?.[col] ?? "—";
            tr.appendChild(td);
        });

        const tdAction = document.createElement("td");
        tdAction.className =
            "px-4 py-2 text-right border-b border-border w-[140px]";

        tdAction.innerHTML = `
            <div class="flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                    onclick="openDrawer('edit', ${index})"
                    class="px-3 py-1.5 text-xs rounded-md border border-border 
                           text-gray-700 hover:bg-gray-100 transition">
                    Edit
                </button>

                <button
                    onclick="deleteRow('${row.id}', ${index})"
                    class="px-3 py-1.5 text-xs rounded-md border border-border 
                           text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition">
                    Delete
                </button>
            </div>
        `;

        tr.appendChild(tdAction);
        tbody.appendChild(tr);
    });
}


// --- 4. Form Drawer Logic ---

function openDrawer(mode, rowIndex = null) {
    const drawer = document.getElementById("formDrawer");
    const formContainer = document.getElementById("dynamicForm");
    const title = document.getElementById("drawer-title");

    formContainer.innerHTML = "";

    editingRowIndex = rowIndex;
    editingRowId = null;

    if (mode === "edit" && rowIndex !== null) {
        title.innerText = "Edit Record";

        const row = currentData.rows[rowIndex];
        editingRowId = row.id;

        currentData.columns.forEach(col => {
            createInput(formContainer, col, row.data?.[col] ?? "");
        });
    } else {
        title.innerText = "Add New Record";
        currentData.columns.forEach(col => {
            createInput(formContainer, col, "");
        });
    }

    drawer.classList.remove("translate-x-full");
}


function createInput(container, label, value) {
    const div = document.createElement("div");
    div.innerHTML = `
        <label class="block text-sm font-medium text-gray-700 mb-1.5">${label}</label>
        <input type="text" name="${label}" value="${value}" 
            class="w-full px-4 py-2.5 bg-gray-50 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-2 focus:ring-primary/20 focus:border-primary focus:bg-white outline-none transition-all placeholder-gray-400"
            placeholder="Enter ${label}...">
    `;
    container.appendChild(div);
}

function closeDrawer() {
    document.getElementById("formDrawer").classList.add("translate-x-full");
    editingRowIndex = null;
}

// --- 5. Submit Logic ---
async function submitForm() {
    const btn = document.getElementById("btn-save");

    const payload = {};
    document.querySelectorAll("#dynamicForm input").forEach(input => {
        payload[input.name] = input.value;
    });

    const previousRows = JSON.parse(JSON.stringify(currentData.rows));

    closeDrawer();

    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<i class="ph-bold ph-spinner animate-spin"></i> Saving...`;

    let tempId = null;
    const isEdit = Boolean(editingRowId);

    try {
        // --------------------
        // OPTIMISTIC CREATE
        // --------------------
        if (!isEdit) {
            tempId = `temp-${Date.now()}`;

            currentData.rows.push({
                id: tempId,
                data: payload,
                __temp: true
            });

            renderTable();
        }

        // --------------------
        // API CALL
        // --------------------
        const res = await fetch(
            editingRowId
                ? `/api/sheets/${currentSheetId}/rows/${editingRowId}/`
                : `/api/sheets/${currentSheetId}/rows/`,
            {
                method: editingRowId ? "PUT" : "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCSRFToken()
                },
                body: JSON.stringify(payload)
            }
        );


        if (res.status === 409) {
            showToast("Row is syncing… please retry in a moment ⏳", "warning");
            return;
        }

        if (!res.ok) throw new Error("Save failed");

        const savedRow = await res.json();

        // --------------------
        // UPDATE STATE
        // --------------------
        if (isEdit) {
            const index = currentData.rows.findIndex(r => r.id === editingRowId);
            if (index !== -1) currentData.rows[index] = savedRow;
        } else {
            const index = currentData.rows.findIndex(r => r.id === tempId);
            if (index !== -1) currentData.rows[index] = savedRow;
        }

        renderTable();
        showToast(isEdit ? "Updated successfully ✨" : "Saved instantly ⚡", "success");

    } catch (err) {
        console.error(err);
        currentData.rows = previousRows;
        renderTable();
        showToast("Save failed — reverted", "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalHTML;
        editingRowIndex = null;
        editingRowId = null;
    }
}


async function deleteRow(rowId, rowIndex) {
    if (!confirm("Delete this row?")) return;

    const previousRows = JSON.parse(JSON.stringify(currentData.rows));

    // optimistic remove
    currentData.rows.splice(rowIndex, 1);
    renderTable();

    try {
        const res = await fetch(`/api/rows/${rowId}/`, {
            method: "DELETE",
            headers: {
                "X-CSRFToken": getCSRFToken()
            }
        });

        if (!res.ok) throw new Error("Delete failed");

        showToast("Row deleted 🗑️", "success");

    } catch (err) {
        console.error(err);
        currentData.rows = previousRows;
        renderTable();
        showToast("Delete failed — reverted", "error");
    }
}


