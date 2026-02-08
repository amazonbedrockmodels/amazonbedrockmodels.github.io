// Global State
let allModels = [];
let allProfiles = [];
let filteredModels = [];
let currentSortColumn = 'modelId';
let currentSortDirection = 'asc';
window.betaModelIds = new Set();

// Filter selections
let selectedProviders = new Set();
let selectedStatus = new Set();
let selectedRegions = new Set();
let selectedInputModalities = new Set();
let selectedOutputModalities = new Set();

// DOM Elements
const searchInput = document.getElementById('searchInput');
const resetFiltersBtn = document.getElementById('resetFilters');
const modelsGrid = document.getElementById('modelsGrid');
const resultsCount = document.getElementById('resultsCount');
const profileModal = document.getElementById('profileModal');
const profilesList = document.getElementById('profilesList');
const modalModelId = document.getElementById('modalModelId');
const lastUpdatedSpan = document.getElementById('lastUpdated');

// Multi-select elements
const multiSelectFilters = {
    provider: {
        trigger: document.getElementById('providerTrigger'),
        dropdown: document.getElementById('providerDropdown'),
        options: document.getElementById('providerOptions'),
        selected: selectedProviders
    },
    status: {
        trigger: document.getElementById('statusTrigger'),
        dropdown: document.getElementById('statusDropdown'),
        options: document.getElementById('statusOptions'),
        selected: selectedStatus
    },
    region: {
        trigger: document.getElementById('regionTrigger'),
        dropdown: document.getElementById('regionDropdown'),
        options: document.getElementById('regionOptions'),
        selected: selectedRegions
    },
    inputModality: {
        trigger: document.getElementById('inputModalityTrigger'),
        dropdown: document.getElementById('inputModalityDropdown'),
        options: document.getElementById('inputModalityOptions'),
        selected: selectedInputModalities
    },
    outputModality: {
        trigger: document.getElementById('outputModalityTrigger'),
        dropdown: document.getElementById('outputModalityDropdown'),
        options: document.getElementById('outputModalityOptions'),
        selected: selectedOutputModalities
    }
};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadData();
    initializeFilters();
    initializeMultiSelectHandlers();
    applyFilters();
});

// Event Listeners
if (searchInput) searchInput.addEventListener('input', applyFilters);
if (resetFiltersBtn) resetFiltersBtn.addEventListener('click', resetFilters);

// Region tooltip handling
let regionTooltip = null;
let betaTooltip = null;
document.addEventListener('mouseover', (e) => {
    if (e.target.classList.contains('region-group')) {
        showRegionTooltip(e.target);
    }
});

document.addEventListener('mouseout', (e) => {
    if (e.target.classList.contains('region-group')) {
        hideRegionTooltip();
    }
});

document.addEventListener('click', (e) => {
    if (e.target.classList.contains('region-group')) {
        e.stopPropagation();
        showRegionTooltip(e.target, true);
    } else if (regionTooltip && !regionTooltip.contains(e.target)) {
        hideRegionTooltip();
    }
});

// Close dropdowns when clicking outside
document.addEventListener('click', (e) => {
    Object.values(multiSelectFilters).forEach(filter => {
        if (!filter.trigger.parentElement.contains(e.target)) {
            filter.dropdown.classList.remove('active');
            filter.trigger.classList.remove('active');
        }
    });
});

/**
 * Load data from JSON files
 */
async function loadData() {
    try {
        const [modelsRes, profilesRes, betaRes] = await Promise.all([
            fetch('data/models.json'),
            fetch('data/profiles.json'),
            fetch('data/beta_models.json').catch(() => ({ ok: true, json: async () => [] }))
        ]);

        if (!modelsRes.ok || !profilesRes.ok) {
            throw new Error('Failed to fetch data files');
        }

        allModels = await modelsRes.json();
        allProfiles = await profilesRes.json();
        const betaModels = await betaRes.json();
        window.betaModelIds = new Set(betaModels.map(m => m.id));

        updateLastUpdatedTime();
        console.log(`Loaded ${allModels.length} models and ${allProfiles.length} profiles`);
    } catch (error) {
        console.error('Error loading data:', error);
        modelsGrid.innerHTML =
            '<div class="loading" style="grid-column: 1/-1; text-align: center; padding: 40px; color: #666;">Error loading data. Please refresh the page.</div>';
    }
}

/**
 * Update last updated timestamp based on file modification time
 */
async function updateLastUpdatedTime() {
    try {
        const response = await fetch('data/models.json', { method: 'HEAD' });
        const lastModified = response.headers.get('last-modified');
        if (lastModified) {
            const date = new Date(lastModified);
            lastUpdatedSpan.textContent = date.toLocaleString();
        } else {
            lastUpdatedSpan.textContent = new Date().toLocaleString();
        }
    } catch (error) {
        lastUpdatedSpan.textContent = new Date().toLocaleString();
    }
}

/**
 * Initialize filter dropdowns with unique values
 */
function initializeFilters() {
    // Populate providers
    const providers = [...new Set(allModels.map(m => m.providerName))].sort();
    multiSelectFilters.provider.options.innerHTML = providers.map(provider => `
        <label class="checkbox-option">
            <input type="checkbox" value="${escapeHtml(provider)}" data-filter="provider"> ${escapeHtml(provider)}
        </label>
    `).join('');

    // Populate status
    const statuses = [...new Set(allModels.map(m => m.modelLifecycle?.status).filter(s => s))].sort();
    multiSelectFilters.status.options.innerHTML = statuses.map(status => `
        <label class="checkbox-option">
            <input type="checkbox" value="${escapeHtml(status)}" data-filter="status"> ${escapeHtml(status)}
        </label>
    `).join('');

    // Populate regions
    const regions = new Set();
    allModels.forEach(m => {
        if (m.regions && Array.isArray(m.regions)) {
            m.regions.forEach(r => regions.add(r));
        }
    });
    const sortedRegions = Array.from(regions).sort();
    multiSelectFilters.region.options.innerHTML = sortedRegions.map(region => `
        <label class="checkbox-option">
            <input type="checkbox" value="${escapeHtml(region)}" data-filter="region"> ${escapeHtml(region)}
        </label>
    `).join('');

    // Populate input modalities
    const inputModalities = new Set();
    allModels.forEach(m => {
        if (m.inputModalities && Array.isArray(m.inputModalities)) {
            m.inputModalities.forEach(mod => inputModalities.add(mod));
        }
    });
    const sortedInputModalities = Array.from(inputModalities).sort();
    multiSelectFilters.inputModality.options.innerHTML = sortedInputModalities.map(modality => `
        <label class="checkbox-option">
            <input type="checkbox" value="${escapeHtml(modality)}" data-filter="inputModality"> ${escapeHtml(modality)}
        </label>
    `).join('');

    // Populate output modalities
    const outputModalities = new Set();
    allModels.forEach(m => {
        if (m.outputModalities && Array.isArray(m.outputModalities)) {
            m.outputModalities.forEach(mod => outputModalities.add(mod));
        }
    });
    const sortedOutputModalities = Array.from(outputModalities).sort();
    multiSelectFilters.outputModality.options.innerHTML = sortedOutputModalities.map(modality => `
        <label class="checkbox-option">
            <input type="checkbox" value="${escapeHtml(modality)}" data-filter="outputModality"> ${escapeHtml(modality)}
        </label>
    `).join('');
}

/**
 * Initialize multi-select dropdown handlers
 */
function initializeMultiSelectHandlers() {
    Object.entries(multiSelectFilters).forEach(([filterName, filter]) => {
        if (!filter.trigger || !filter.dropdown || !filter.options) {
            console.warn(`Missing elements for filter: ${filterName}`);
            return;
        }

        // Toggle dropdown
        filter.trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            const isActive = filter.dropdown.classList.contains('active');

            // Close all dropdowns
            Object.values(multiSelectFilters).forEach(f => {
                if (f.dropdown) f.dropdown.classList.remove('active');
                if (f.trigger) f.trigger.classList.remove('active');
            });

            // Toggle current dropdown
            if (!isActive) {
                filter.dropdown.classList.add('active');
                filter.trigger.classList.add('active');
            }
        });

        // Handle checkbox changes
        filter.options.addEventListener('change', (e) => {
            if (e.target.type === 'checkbox') {
                const value = e.target.value;
                if (e.target.checked) {
                    filter.selected.add(value);
                } else {
                    filter.selected.delete(value);
                }
                updateTriggerText(filterName);
                applyFilters();
            }
        });

        // Handle search within dropdown (if search box exists)
        const searchBox = filter.dropdown.querySelector('.dropdown-search');
        if (searchBox) {
            searchBox.addEventListener('input', (e) => {
                const searchTerm = e.target.value.toLowerCase();
                const options = filter.options.querySelectorAll('.checkbox-option');
                options.forEach(option => {
                    const text = option.textContent.toLowerCase();
                    option.style.display = text.includes(searchTerm) ? 'flex' : 'none';
                });
            });

            // Prevent dropdown from closing when clicking search box
            searchBox.addEventListener('click', (e) => {
                e.stopPropagation();
            });
        }
    });
}

/**
 * Update trigger text based on selected values
 */
function updateTriggerText(filterName) {
    const filter = multiSelectFilters[filterName];
    const selectedText = filter.trigger.querySelector('.selected-text');
    const count = filter.selected.size;

    const labels = {
        provider: { all: 'All Providers', one: 'provider', many: 'providers' },
        status: { all: 'All Status', one: 'status', many: 'status' },
        region: { all: 'All Regions', one: 'region', many: 'regions' },
        inputModality: { all: 'All Inputs', one: 'input', many: 'inputs' },
        outputModality: { all: 'All Outputs', one: 'output', many: 'outputs' }
    };

    const label = labels[filterName];

    if (count === 0) {
        selectedText.textContent = label.all;
    } else if (count === 1) {
        selectedText.textContent = Array.from(filter.selected)[0];
    } else {
        selectedText.textContent = `${count} ${label.many}`;
    }
}

/**
 * Apply all active filters
 */
function applyFilters() {
    const searchTerm = (searchInput?.value || '').toLowerCase();

    filteredModels = allModels.filter(model => {
        // Search filter
        if (searchTerm) {
            const matchesSearch =
                (model.modelId && model.modelId.toLowerCase().includes(searchTerm)) ||
                (model.modelName && model.modelName.toLowerCase().includes(searchTerm));
            if (!matchesSearch) return false;
        }

        // Provider filter
        if (selectedProviders.size > 0) {
            if (!selectedProviders.has(model.providerName)) {
                return false;
            }
        }

        // Status filter
        if (selectedStatus.size > 0) {
            const modelStatus = model.modelLifecycle?.status || 'ACTIVE';
            if (!selectedStatus.has(modelStatus)) {
                return false;
            }
        }

        // Region filter
        if (selectedRegions.size > 0) {
            if (!model.regions || !model.regions.some(r => selectedRegions.has(r))) {
                return false;
            }
        }

        // Input modality filter
        if (selectedInputModalities.size > 0) {
            if (!model.inputModalities || !model.inputModalities.some(m => selectedInputModalities.has(m))) {
                return false;
            }
        }

        // Output modality filter
        if (selectedOutputModalities.size > 0) {
            if (!model.outputModalities || !model.outputModalities.some(m => selectedOutputModalities.has(m))) {
                return false;
            }
        }

        return true;
    });

    // Sort
    if (currentSortColumn) {
        sortModels(currentSortColumn);
    }

    renderTable();
    updateResultsCount();
}

/**
 * Sort models by column
 */
function sortTable(column) {
    if (currentSortColumn === column) {
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        currentSortColumn = column;
        currentSortDirection = 'asc';
    }
    applyFilters();
}

/**
 * Sort filtered models
 */
function sortModels(column) {
    filteredModels.sort((a, b) => {
        let aValue, bValue;

        switch (column) {
            case 'modelId':
                aValue = a.modelId || '';
                bValue = b.modelId || '';
                break;
            case 'modelName':
                aValue = a.modelName || '';
                bValue = b.modelName || '';
                break;
            case 'providerName':
                aValue = a.providerName || '';
                bValue = b.providerName || '';
                break;
            default:
                return 0;
        }

        if (typeof aValue === 'string') {
            aValue = aValue.toLowerCase();
            bValue = bValue.toLowerCase();
        }

        if (aValue < bValue) {
            return currentSortDirection === 'asc' ? -1 : 1;
        } else if (aValue > bValue) {
            return currentSortDirection === 'asc' ? 1 : -1;
        }
        return 0;
    });
}

/**
 * Render the models as cards
 */
function renderTable() {
    if (filteredModels.length === 0) {
        modelsGrid.innerHTML =
            '<div class="loading" style="grid-column: 1/-1; text-align: center; padding: 40px; color: #666;">No models found matching your filters.</div>';
        return;
    }

    modelsGrid.innerHTML = filteredModels
        .map(model => createModelCard(model))
        .join('');
}

/**
 * Format regions - group by prefix if more than 4 regions
 */
function formatRegions(regions) {
    if (!regions || regions.length === 0) return 'None';
    if (regions.length <= 4) return regions.join(', ');

    // Group by prefix (ap, us, eu, ca, sa, etc.)
    const grouped = {};
    regions.forEach(region => {
        const prefix = region.split('-')[0].toUpperCase();
        if (!grouped[prefix]) {
            grouped[prefix] = [];
        }
        grouped[prefix].push(region);
    });

    // Sort prefixes and format as "PREFIX (count)" with custom tooltips
    return Object.keys(grouped)
        .sort()
        .map(prefix => {
            const regionList = grouped[prefix].sort().join(', ');
            return `<span class="region-group" data-regions="${escapeHtml(regionList)}">${prefix} (${grouped[prefix].length})</span>`;
        })
        .join(', ');
}

/**
 * Create a card for a model
 */
function createModelCard(model) {
    const status = model.modelLifecycle?.status || 'ACTIVE';
    const streaming = model.responseStreamingSupported;
    const inputModalities = (model.inputModalities || []).join(', ');
    const outputModalities = (model.outputModalities || []).join(', ');
    const regions = formatRegions(model.regions);
    const statusClass = status === 'ACTIVE' ? 'status-active' : 'status-legacy';
    const isBeta = window.betaModelIds && window.betaModelIds.has(model.modelId);

    const profilesButton = hasProfilesForModel(model.modelId)
        ? `<button class="profiles-btn" onclick="openProfilesModal('${escapeHtml(model.modelId)}')"><i class="fas fa-book"></i> Profiles</button>`
        : `<button class="profiles-btn" disabled><i class="fas fa-ban"></i> No Profiles</button>`;

    return `
        <div class="model-card">
            <div class="model-card-header">
                <div class="model-card-title">
                    <div class="model-id">${escapeHtml(model.modelId)}</div>
                    <div class="model-name">${escapeHtml(model.modelName || 'N/A')}</div>
                </div>
                <span class="model-provider">${escapeHtml(model.providerName || 'N/A')}</span>
            </div>
            <div class="model-card-body">
                <div class="model-card-row model-card-row-inline">
                    <div class="model-card-inline-section">
                        <span class="model-card-label"><i class="fas fa-arrow-right"></i> Input</span>
                        <div class="model-card-content">${inputModalities || 'None'}</div>
                    </div>
                    <div class="model-card-inline-section">
                        <span class="model-card-label"><i class="fas fa-arrow-left"></i> Output</span>
                        <div class="model-card-content">${outputModalities || 'None'}</div>
                    </div>
                </div>
                <div class="model-card-row">
                    <span class="model-card-label"><i class="fas fa-globe"></i> Regions</span>
                    <div class="model-card-content regions-content">${regions || 'None'}</div>
                </div>
            </div>
            <div class="model-card-footer">
                <div style="display: flex; gap: 8px; flex: 1;">
                    <span class="status-badge ${statusClass}"><i class="fas fa-circle"></i> ${escapeHtml(status)}</span>
                    ${streaming ? '<span class="streaming-badge"><i class="fas fa-stream"></i> Streaming</span>' : ''}
                    ${isBeta ? '<span class="beta-badge" onclick="showBetaTooltip(event)"><i class="fas fa-star"></i> Beta</span>' : ''}
                </div>
                ${profilesButton}
            </div>
        </div>
    `;
}

/**
 * Check if model has any profiles
 */
function hasProfilesForModel(modelId) {
    return allProfiles.some(profile => {
        if (profile.models && Array.isArray(profile.models)) {
            return profile.models.some(m => {
                // m can be either a string or an object with modelArn property
                const arn = typeof m === 'string' ? m : (m.modelArn || '');
                return arn.includes(modelId);
            });
        }
        return false;
    });
}

/**
 * Open the profiles modal for a model
 */
function openProfilesModal(modelId) {
    modalModelId.textContent = escapeHtml(modelId);

    // Filter profiles for this model
    const modelProfiles = allProfiles.filter(profile => {
        if (profile.models && Array.isArray(profile.models)) {
            return profile.models.some(m => {
                const arn = typeof m === 'string' ? m : (m.modelArn || '');
                return arn.includes(modelId);
            });
        }
        return false;
    });

    // Group by inferenceProfileId and merge regions
    const groupedProfiles = {};
    modelProfiles.forEach(profile => {
        const id = profile.inferenceProfileId;
        if (!groupedProfiles[id]) {
            groupedProfiles[id] = { ...profile, regions: [profile.region] };
        } else {
            groupedProfiles[id].regions.push(profile.region);
        }
    });

    const profilesArr = Object.values(groupedProfiles);

    if (profilesArr.length === 0) {
        profilesList.innerHTML = '<p>No inference profiles available for this model.</p>';
    } else {
        profilesList.innerHTML = profilesArr
            .map(profile => createProfileItem(profile))
            .join('');
    }

    profileModal.classList.remove('hidden');
}

/**
 * Create a profile item in the modal
 */
function createProfileItem(profile) {
    const createdDate = profile.createdAt
        ? new Date(profile.createdAt).toLocaleDateString()
        : 'N/A';
    const status = profile.status || 'ACTIVE';
    const type = profile.type || 'SYSTEM_DEFINED';
    const regions = Array.isArray(profile.regions)
        ? profile.regions.join(', ')
        : escapeHtml(profile.region || 'N/A');

    return `
        <div class="profile-item">
            <div class="profile-name">${escapeHtml(profile.inferenceProfileName || 'N/A')}</div>
            <div class="profile-description">${escapeHtml(profile.description || 'No description provided')}</div>
            <div class="profile-id-section">
                <span class="profile-id-label">Profile ID:</span>
                <span class="profile-id-value">${escapeHtml(profile.inferenceProfileId)}</span>
                <button class="copy-btn" onclick="copyToClipboard(this, '${escapeHtml(profile.inferenceProfileId)}')">Copy</button>
            </div>
            <div class="profile-meta">
                <div class="profile-meta-item">
                    <span class="profile-meta-label">Regions:</span>
                    <span class="profile-meta-value">${regions}</span>
                </div>
                <div class="profile-meta-item">
                    <span class="profile-meta-label">Status:</span>
                    <span class="profile-meta-value">${escapeHtml(status)}</span>
                </div>
                <div class="profile-meta-item">
                    <span class="profile-meta-label">Type:</span>
                    <span class="profile-meta-value">${escapeHtml(type)}</span>
                </div>
                <div class="profile-meta-item">
                    <span class="profile-meta-label">Created:</span>
                    <span class="profile-meta-value">${createdDate}</span>
                </div>
            </div>
        </div>
    `;
}

/**
 * Close the profiles modal
 */
function closeModal() {
    profileModal.classList.add('hidden');
}

/**
 * Copy text to clipboard
 */
function copyToClipboard(button, text) {
    navigator.clipboard.writeText(text).then(() => {
        const originalText = button.textContent;
        button.textContent = 'Copied!';
        button.classList.add('copied');
        setTimeout(() => {
            button.textContent = originalText;
            button.classList.remove('copied');
        }, 2000);
    });
}

/**
 * Update results count display
 */
function updateResultsCount() {
    const total = allModels.length;
    const filtered = filteredModels.length;
    if (filtered === total) {
        resultsCount.textContent = `Showing all ${total} models`;
    } else {
        resultsCount.textContent = `Showing ${filtered} of ${total} models`;
    }
}

/**
 * Show region tooltip
 */
function showRegionTooltip(element, sticky = false) {
    hideRegionTooltip();

    const regions = element.getAttribute('data-regions');
    if (!regions) return;

    regionTooltip = document.createElement('div');
    regionTooltip.className = 'region-tooltip' + (sticky ? ' sticky' : '');

    // Split regions and display in column format
    const regionList = regions.split(', ').map(r => `<div class="region-item">${escapeHtml(r)}</div>`).join('');
    regionTooltip.innerHTML = regionList;

    document.body.appendChild(regionTooltip);

    const rect = element.getBoundingClientRect();
    const tooltipRect = regionTooltip.getBoundingClientRect();

    let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
    let top = rect.bottom + 8;

    // Keep tooltip in viewport
    if (left + tooltipRect.width > window.innerWidth - 10) {
        left = window.innerWidth - tooltipRect.width - 10;
    }
    if (left < 10) {
        left = 10;
    }

    regionTooltip.style.left = left + 'px';
    regionTooltip.style.top = top + 'px';

    // Force reflow for transition
    regionTooltip.offsetHeight;
    regionTooltip.classList.add('visible');
}

/**
 * Hide region tooltip
 */
function hideRegionTooltip() {
    if (regionTooltip) {
        // Don't hide if it's sticky (clicked)
        if (regionTooltip.classList.contains('sticky')) return;

        regionTooltip.classList.remove('visible');
        setTimeout(() => {
            if (regionTooltip && regionTooltip.parentNode) {
                regionTooltip.parentNode.removeChild(regionTooltip);
            }
            regionTooltip = null;
        }, 200);
    }
}

/**
 * Show beta tooltip
 */
function showBetaTooltip(event) {
    event.stopPropagation();
    hideBetaTooltip();

    const element = event.target.closest('.beta-badge');
    if (!element) return;

    betaTooltip = document.createElement('div');
    betaTooltip.className = 'beta-tooltip sticky';
    betaTooltip.innerHTML = "This model doesn't appear in Amazon Bedrock official documentation. Features may not be complete.";

    document.body.appendChild(betaTooltip);

    const rect = element.getBoundingClientRect();
    const tooltipRect = betaTooltip.getBoundingClientRect();

    let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
    let top = rect.bottom + 8;

    // Keep tooltip in viewport
    if (left + tooltipRect.width > window.innerWidth - 10) {
        left = window.innerWidth - tooltipRect.width - 10;
    }
    if (left < 10) {
        left = 10;
    }

    betaTooltip.style.left = left + 'px';
    betaTooltip.style.top = top + 'px';

    // Force reflow for transition
    betaTooltip.offsetHeight;
    betaTooltip.classList.add('visible');
}

/**
 * Hide beta tooltip
 */
function hideBetaTooltip() {
    if (betaTooltip) {
        betaTooltip.classList.remove('visible');
        setTimeout(() => {
            if (betaTooltip && betaTooltip.parentNode) {
                betaTooltip.parentNode.removeChild(betaTooltip);
            }
            betaTooltip = null;
        }, 200);
    }
}

// Close beta tooltip when clicking elsewhere
document.addEventListener('click', (e) => {
    if (betaTooltip && !e.target.closest('.beta-badge') && !betaTooltip.contains(e.target)) {
        hideBetaTooltip();
    }
});

/**
 * Reset all filters
 */
function resetFilters() {
    searchInput.value = '';

    // Clear all selected values
    selectedProviders.clear();
    selectedStatus.clear();
    selectedRegions.clear();
    selectedInputModalities.clear();
    selectedOutputModalities.clear();

    // Uncheck all checkboxes
    Object.values(multiSelectFilters).forEach(filter => {
        const checkboxes = filter.options.querySelectorAll('input[type=\"checkbox\"]');
        checkboxes.forEach(cb => cb.checked = false);
        updateTriggerText(Object.keys(multiSelectFilters).find(key => multiSelectFilters[key] === filter));
    });

    // Clear search boxes in dropdowns
    document.querySelectorAll('.dropdown-search').forEach(search => {
        search.value = '';
        // Reset visibility of all options
        const options = search.closest('.multi-select-dropdown').querySelectorAll('.checkbox-option');
        options.forEach(option => option.style.display = 'flex');
    });

    currentSortColumn = null;
    currentSortDirection = 'asc';
    applyFilters();
}

/**
 * Escape HTML special characters
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// Close modal when clicking outside of it
window.addEventListener('click', event => {
    if (event.target === profileModal) {
        closeModal();
    }
});
