document.addEventListener("DOMContentLoaded", () => {
    const cache = new Map();
    const CACHE_EXPIRY = 5 * 60 * 1000;
    const FIELD_OPTIONS = [
        { value: "all", label: "All Fields" },
        { value: "arxiv_id", label: "arXiv ID" },
        { value: "title", label: "Title" },
        { value: "dataset_name", label: "Dataset Name" },
        { value: "dataset_entity", label: "Dataset Entity" },
        { value: "task", label: "Task" },
        { value: "data_type", label: "Data Type" },
    ];
    const MATCH_OPTIONS = [
        { value: "contains", label: "Contains" },
        { value: "exact", label: "Exact" },
        { value: "prefix", label: "Prefix" },
    ];

    const getApiUrl = () => {
        const hostname = window.location.hostname;
        if (hostname === "chatpd-web.github.io" || hostname.includes("github.io")) {
            return "https://testweb.241814.xyz:5000";
        }
        if (hostname === "localhost" || hostname === "127.0.0.1") {
            return "";
        }
        return "https://testweb.241814.xyz:5000";
    };

    const getBaseUrl = () => {
        const path = window.location.pathname;
        if (path.includes("/chatpd-web/")) {
            return "/chatpd-web";
        }
        return "";
    };

    const apiUrl = getApiUrl();
    const baseUrl = getBaseUrl();

    const form = document.getElementById("search-form");
    const keywordsInput = document.getElementById("keywords");
    const resetButton = document.getElementById("reset-filters");
    const resultsList = document.getElementById("results-list");
    const resultsCount = document.getElementById("results-count");
    const resultStats = document.getElementById("search-stats");
    const pageSelector = document.getElementById("page-selector");
    const prevPageBtn = document.getElementById("prev-page");
    const nextPageBtn = document.getElementById("next-page");
    const dataTypeFilter = document.getElementById("data-type-filter");
    const taskFilter = document.getElementById("task-filter");
    const dataStatusText = document.getElementById("data-status-text");
    const refreshDataStatusBtn = document.getElementById("refresh-data-status");

    const toggleAdvancedBtn = document.getElementById("toggle-advanced");
    const advancedPanel = document.getElementById("advanced-search-panel");
    const addConditionBtn = document.getElementById("add-condition");
    const advancedConditions = document.getElementById("advanced-conditions");
    const conditionLogic = document.getElementById("condition-logic");
    const includeStatsInput = document.getElementById("include-stats");
    const sortByInput = document.getElementById("sort-by");
    const sortOrderInput = document.getElementById("sort-order");

    let currentPage = 1;
    let totalPages = 1;
    let selectedDataType = "All";
    let selectedTask = "All";

    function getCachedData(key) {
        const item = cache.get(key);
        if (item && Date.now() - item.timestamp < CACHE_EXPIRY) {
            return item.data;
        }
        cache.delete(key);
        return null;
    }

    function setCachedData(key, data) {
        cache.set(key, { data, timestamp: Date.now() });
    }

    function debounce(func, wait) {
        let timeout;
        return (...args) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => func(...args), wait);
        };
    }

    function escapeHtml(text) {
        return (text ?? "")
            .toString()
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function updateNavigationAndAssets() {
        document.querySelectorAll(".top-nav a").forEach((link) => {
            if (link.getAttribute("href") === "./") {
                link.setAttribute("href", baseUrl + "/" || "./");
            } else if (link.getAttribute("href") === "datasets") {
                link.setAttribute("href", baseUrl + "/datasets");
            }
        });
        const cssLink = document.getElementById("css-link");
        if (baseUrl && cssLink) {
            cssLink.href = `${baseUrl}/static/css/styles.css`;
        }
    }

    function showLoading() {
        resultsList.innerHTML = '<div class="loading">Loading...</div>';
    }

    function formatSize(bytes) {
        if (!bytes || bytes <= 0) return "0 B";
        const units = ["B", "KB", "MB", "GB"];
        let size = bytes;
        let idx = 0;
        while (size >= 1024 && idx < units.length - 1) {
            size /= 1024;
            idx += 1;
        }
        return `${size.toFixed(1)} ${units[idx]}`;
    }

    function fetchDataStatus() {
        dataStatusText.textContent = "数据状态加载中...";
        fetch(`${apiUrl}/api/data-status`)
            .then((response) => response.json())
            .then((data) => {
                const sourceMtime = data.source_json_mtime || "N/A";
                const dbMtime = data.database_mtime || "N/A";
                const totalRecords = Number(data.total_records || 0).toLocaleString();
                const totalDatasets = Number(data.total_datasets || 0).toLocaleString();
                const sourceSize = formatSize(data.source_json_size_bytes || 0);
                const dbSize = formatSize(data.database_size_bytes || 0);
                dataStatusText.textContent =
                    `当前数据源: from_db | 记录数: ${totalRecords} | 数据集数: ${totalDatasets} | JSON更新时间: ${sourceMtime} | DB更新时间: ${dbMtime} | JSON大小: ${sourceSize} | DB大小: ${dbSize}`;
            })
            .catch((error) => {
                console.error("Error fetching data status:", error);
                dataStatusText.textContent = "数据状态获取失败，请稍后重试。";
            });
    }

    function updateActiveFilter(container, activeLink) {
        container.querySelectorAll(".filter-link").forEach((link) => link.classList.remove("active"));
        if (activeLink) {
            activeLink.classList.add("active");
        }
    }

    function createConditionRow(initial = { field: "all", match_mode: "contains", value: "" }) {
        const row = document.createElement("div");
        row.className = "condition-row";

        const fieldSelect = document.createElement("select");
        fieldSelect.className = "condition-field";
        FIELD_OPTIONS.forEach((option) => {
            const optionNode = document.createElement("option");
            optionNode.value = option.value;
            optionNode.textContent = option.label;
            if (option.value === initial.field) optionNode.selected = true;
            fieldSelect.appendChild(optionNode);
        });

        const matchSelect = document.createElement("select");
        matchSelect.className = "condition-match";
        MATCH_OPTIONS.forEach((option) => {
            const optionNode = document.createElement("option");
            optionNode.value = option.value;
            optionNode.textContent = option.label;
            if (option.value === initial.match_mode) optionNode.selected = true;
            matchSelect.appendChild(optionNode);
        });

        const valueInput = document.createElement("input");
        valueInput.className = "condition-value";
        valueInput.type = "text";
        valueInput.placeholder = "Condition value";
        valueInput.value = initial.value || "";

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "remove-condition";
        removeButton.textContent = "Remove";
        removeButton.addEventListener("click", () => {
            row.remove();
            currentPage = 1;
            fetchResults();
        });

        [fieldSelect, matchSelect, valueInput].forEach((node) => {
            node.addEventListener("change", () => {
                currentPage = 1;
                fetchResults();
            });
        });
        valueInput.addEventListener("input", debounce(() => {
            currentPage = 1;
            fetchResults();
        }, 400));

        row.appendChild(fieldSelect);
        row.appendChild(matchSelect);
        row.appendChild(valueInput);
        row.appendChild(removeButton);
        advancedConditions.appendChild(row);
    }

    function collectConditions() {
        const conditions = [];
        advancedConditions.querySelectorAll(".condition-row").forEach((row) => {
            const field = row.querySelector(".condition-field")?.value || "all";
            const match_mode = row.querySelector(".condition-match")?.value || "contains";
            const value = (row.querySelector(".condition-value")?.value || "").trim();
            if (value) {
                conditions.push({ field, match_mode, value });
            }
        });

        if (selectedDataType !== "All") {
            conditions.push({ field: "data_type", match_mode: "exact", value: selectedDataType });
        }
        if (selectedTask !== "All") {
            conditions.push({ field: "task", match_mode: "exact", value: selectedTask });
        }
        return conditions;
    }

    function renderStats(stats) {
        if (!resultStats) return;
        if (!stats) {
            resultStats.innerHTML = "";
            return;
        }

        const taskTop = (stats.task_distribution || [])
            .slice(0, 4)
            .map((item) => `${escapeHtml(item.name)} (${item.count})`)
            .join(" | ");
        const dataTypeTop = (stats.data_type_distribution || [])
            .slice(0, 4)
            .map((item) => `${escapeHtml(item.name)} (${item.count})`)
            .join(" | ");

        resultStats.innerHTML = `
            <div><strong>Top Tasks:</strong> ${taskTop || "N/A"}</div>
            <div><strong>Top Data Types:</strong> ${dataTypeTop || "N/A"}</div>
        `;
    }

    function populateDataTypeFilter(dataTypes) {
        dataTypeFilter.querySelectorAll('.filter-link:not([data-type="All"])').forEach((link) => link.remove());
        dataTypes.forEach((item) => {
            const link = document.createElement("a");
            link.href = "#";
            link.dataset.type = item.data_type;
            link.textContent = `${item.data_type} (${item.count})`;
            link.className = "filter-link";
            if (item.data_type === selectedDataType) {
                link.classList.add("active");
            }
            link.addEventListener("click", (event) => {
                event.preventDefault();
                selectedDataType = item.data_type;
                currentPage = 1;
                updateActiveFilter(dataTypeFilter, link);
                fetchResults();
            });
            dataTypeFilter.appendChild(link);
        });
    }

    function populateTaskFilter(tasks) {
        taskFilter.querySelectorAll('.filter-link:not([data-task="All"])').forEach((link) => link.remove());
        tasks.forEach((item) => {
            const link = document.createElement("a");
            link.href = "#";
            link.dataset.task = item.task;
            link.textContent = `${item.task} (${item.count})`;
            link.className = "filter-link";
            if (item.task === selectedTask) {
                link.classList.add("active");
            }
            link.addEventListener("click", (event) => {
                event.preventDefault();
                selectedTask = item.task;
                currentPage = 1;
                updateActiveFilter(taskFilter, link);
                fetchResults();
            });
            taskFilter.appendChild(link);
        });
    }

    function initAllFilterLinks() {
        const dataTypeAllLink = dataTypeFilter.querySelector('a[data-type="All"]');
        const taskAllLink = taskFilter.querySelector('a[data-task="All"]');

        dataTypeAllLink?.addEventListener("click", (event) => {
            event.preventDefault();
            selectedDataType = "All";
            currentPage = 1;
            updateActiveFilter(dataTypeFilter, dataTypeAllLink);
            fetchResults();
        });

        taskAllLink?.addEventListener("click", (event) => {
            event.preventDefault();
            selectedTask = "All";
            currentPage = 1;
            updateActiveFilter(taskFilter, taskAllLink);
            fetchResults();
        });
    }

    function initializeFilters() {
        initAllFilterLinks();
        fetch(`${apiUrl}/api/filters`)
            .then((response) => response.json())
            .then((data) => {
                populateDataTypeFilter(data.top_data_types || []);
                populateTaskFilter(data.top_tasks || []);
                initAllFilterLinks();
            })
            .catch((error) => {
                console.error("Error fetching filters:", error);
            });
    }

    function displayResults(results) {
        if (!results || results.length === 0) {
            resultsList.innerHTML = "<p>No results found.</p>";
            return;
        }

        const fragments = [];
        results.forEach((result) => {
            let displayTitle = (result.title || "").trim();
            if (!displayTitle || displayTitle === "None" || displayTitle === "null") {
                displayTitle = result.arxiv_id ? `arXiv:${result.arxiv_id}` : (result.dataset_name || "Research Study");
            }

            const titleHtml = result.arxiv_id
                ? `<h4><a href="https://arxiv.org/abs/${encodeURIComponent(result.arxiv_id)}" target="_blank" rel="noopener noreferrer">${escapeHtml(displayTitle)}</a></h4>`
                : `<h4>${escapeHtml(displayTitle)}</h4>`;

            let datasetHtml = "<p><strong>Dataset Name:</strong> N/A</p>";
            if (result.dataset_entity) {
                const datasetUrl = `${baseUrl}/dataset/${encodeURIComponent(result.dataset_entity)}`;
                datasetHtml = `<p><strong>Dataset Entity:</strong> <a href="${datasetUrl}">${escapeHtml(result.dataset_entity)}</a></p>`;
            } else if (result.dataset_name) {
                datasetHtml = `<p><strong>Dataset Name:</strong> ${escapeHtml(result.dataset_name)}</p>`;
            }

            const extraFields = [
                result.arxiv_id
                    ? `<p><strong>arXiv ID:</strong> <a href="https://arxiv.org/abs/${encodeURIComponent(result.arxiv_id)}" target="_blank" rel="noopener noreferrer">${escapeHtml(result.arxiv_id)}</a></p>`
                    : "",
                result.dataset_url
                    ? `<p><strong>Dataset URL:</strong> <a href="${escapeHtml(result.dataset_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(result.dataset_url)}</a></p>`
                    : "",
                result.task ? `<p><strong>Task:</strong> ${escapeHtml(result.task)}</p>` : "",
                result.data_type ? `<p><strong>Data Type:</strong> ${escapeHtml(result.data_type)}</p>` : "",
                result.scale ? `<p><strong>Data Scale:</strong> ${escapeHtml(result.scale)}</p>` : "",
                result.location ? `<p><strong>Location:</strong> ${escapeHtml(result.location)}</p>` : "",
                result.dataset_summary ? `<p><strong>Summary:</strong> ${escapeHtml(result.dataset_summary)}</p>` : "",
                result.other_info ? `<p><strong>Other Information:</strong> ${escapeHtml(result.other_info)}</p>` : "",
            ]
                .filter(Boolean)
                .join("");

            fragments.push(`<article class="result-item">${titleHtml}${datasetHtml}${extraFields}</article>`);
        });
        resultsList.innerHTML = fragments.join("");
    }

    function populatePageSelector() {
        pageSelector.innerHTML = "";
        if (totalPages <= 0) {
            const option = document.createElement("option");
            option.value = 1;
            option.textContent = "Page 1 of 1";
            pageSelector.appendChild(option);
            return;
        }
        for (let i = 1; i <= totalPages; i += 1) {
            const option = document.createElement("option");
            option.value = i;
            option.textContent = `Page ${i} of ${totalPages}`;
            if (i === currentPage) option.selected = true;
            pageSelector.appendChild(option);
        }
    }

    function updatePaginationButtons() {
        prevPageBtn.disabled = currentPage <= 1;
        nextPageBtn.disabled = currentPage >= totalPages;
        pageSelector.disabled = totalPages <= 1;
    }

    function buildQueryParams() {
        const keywords = keywordsInput.value.trim();
        const params = new URLSearchParams({
            q: keywords,
            field: "all",
            match_mode: "contains",
            page: currentPage,
            per_page: 10,
            logic: conditionLogic.value || "and",
            sort_by: sortByInput.value || "title",
            sort_order: sortOrderInput.value || "asc",
            include_stats: includeStatsInput.checked ? "true" : "false",
        });
        const conditions = collectConditions();
        if (conditions.length > 0) {
            params.set("conditions", JSON.stringify(conditions));
        }
        return params;
    }

    function fetchResults() {
        const params = buildQueryParams();
        const cacheKey = params.toString();
        const cached = getCachedData(cacheKey);
        if (cached) {
            displayResults(cached.results);
            renderStats(cached.stats);
            totalPages = cached.total_pages;
            resultsCount.textContent = `Search Results: ${cached.results_count} total items (${cached.results.length} items on this page)`;
            populatePageSelector();
            updatePaginationButtons();
            return;
        }

        showLoading();
        fetch(`${apiUrl}/api/query?${params.toString()}`)
            .then((response) => {
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return response.json();
            })
            .then((data) => {
                setCachedData(cacheKey, data);
                displayResults(data.results);
                renderStats(data.stats);
                totalPages = data.total_pages || 1;
                resultsCount.textContent = `Search Results: ${data.results_count} total items (${data.results.length} items on this page)`;
                populatePageSelector();
                updatePaginationButtons();
            })
            .catch((error) => {
                console.error("Error fetching results:", error);
                resultsList.innerHTML = "<p>Error fetching results. Please try again.</p>";
                resultsCount.textContent = "Search Results: 0 total items (0 items on this page)";
                renderStats(null);
            });
    }

    const debouncedSearch = debounce(() => {
        currentPage = 1;
        fetchResults();
    }, 350);

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        currentPage = 1;
        fetchResults();
    });
    keywordsInput.addEventListener("input", debouncedSearch);
    prevPageBtn.addEventListener("click", () => {
        if (currentPage > 1) {
            currentPage -= 1;
            fetchResults();
        }
    });
    nextPageBtn.addEventListener("click", () => {
        if (currentPage < totalPages) {
            currentPage += 1;
            fetchResults();
        }
    });
    pageSelector.addEventListener("change", () => {
        currentPage = parseInt(pageSelector.value, 10) || 1;
        fetchResults();
    });

    toggleAdvancedBtn.addEventListener("click", () => {
        const isHidden = advancedPanel.hidden;
        advancedPanel.hidden = !isHidden;
        toggleAdvancedBtn.setAttribute("aria-expanded", String(isHidden));
    });
    addConditionBtn.addEventListener("click", () => createConditionRow());
    [conditionLogic, sortByInput, sortOrderInput, includeStatsInput].forEach((node) => {
        node.addEventListener("change", () => {
            currentPage = 1;
            fetchResults();
        });
    });
    resetButton.addEventListener("click", () => {
        keywordsInput.value = "";
        conditionLogic.value = "and";
        sortByInput.value = "title";
        sortOrderInput.value = "asc";
        includeStatsInput.checked = true;
        selectedDataType = "All";
        selectedTask = "All";
        updateActiveFilter(dataTypeFilter, dataTypeFilter.querySelector('a[data-type="All"]'));
        updateActiveFilter(taskFilter, taskFilter.querySelector('a[data-task="All"]'));
        advancedConditions.innerHTML = "";
        createConditionRow();
        currentPage = 1;
        fetchResults();
    });

    updateNavigationAndAssets();
    createConditionRow();
    initializeFilters();
    fetchDataStatus();
    refreshDataStatusBtn?.addEventListener("click", fetchDataStatus);
    fetchResults();
});

