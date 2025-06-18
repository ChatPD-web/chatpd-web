document.addEventListener('DOMContentLoaded', () => {
    // API URL配置 - 本地开发使用相对路径，生产环境使用绝对URL
    const getApiUrl = () => {
        const hostname = window.location.hostname;
        if (hostname === 'chatpd-web.github.io' || hostname.includes('github.io')) {
            // GitHub Pages deployment - use remote API server
            return 'https://testweb.241814.xyz:5000';
        } else if (hostname === 'localhost' || hostname === '127.0.0.1') {
            // Local development - use relative paths
            return '';
        } else {
            // Custom domain or other environments
            return 'https://testweb.241814.xyz:5000';
        }
    };
    
    const apiUrl = getApiUrl();
    
    // Get base URL for navigation links
    const getBaseUrl = () => {
        const path = window.location.pathname;
        if (path.includes('/chatpd-web/')) {
            // GitHub Pages deployment
            return '/chatpd-web';
        }
        // Local development
        return '';
    };
    
    const baseUrl = getBaseUrl();
    
    // Update navigation links if present
    if (document.querySelector('.top-nav')) {
        document.querySelectorAll('.top-nav a').forEach(link => {
            if (link.getAttribute('href') === './') {
                link.setAttribute('href', baseUrl + '/' || './');
            } else if (link.getAttribute('href') === 'datasets') {
                link.setAttribute('href', baseUrl + '/datasets');
            }
        });
    }
    
    const form = document.getElementById('search-form');
    const resultsList = document.getElementById('results-list');
    const resultsCount = document.getElementById('results-count');
    const pageSelector = document.getElementById('page-selector');
    const prevPageBtn = document.getElementById('prev-page');
    const nextPageBtn = document.getElementById('next-page');
    const dataTypeFilter = document.getElementById('data-type-filter');
    const taskFilter = document.getElementById('task-filter');

    let currentPage = 1;
    let totalPages = 1;
    let selectedDataType = 'All';
    let selectedTask = 'All';
    let keywords = '';

    // 初始化过滤器
    initializeFilters();

    // 初始化过滤器
    function initializeFilters() {
        // 确保初始的 All 链接有正确的属性
        const dataTypeAllLink = dataTypeFilter.querySelector('a[data-type="All"]');
        if (dataTypeAllLink) {
            dataTypeAllLink.dataset.type = 'All';
        }
        
        const taskAllLink = taskFilter.querySelector('a[data-task="All"]');
        if (taskAllLink) {
            taskAllLink.dataset.task = 'All';
        }

        // 初始化 All 链接的事件监听
        initializeAllLinks();

        // 获取 Data Types 和 Tasks
        fetch(`${apiUrl}/api/filters`)
            .then(response => response.json())
            .then(data => {
                populateDataTypeFilter(data.top_data_types);
                populateTaskFilter(data.top_tasks);
                // 重新初始化 All 链接，以防它们被覆盖
                initializeAllLinks();
            })
            .catch(error => {
                console.error('Error fetching filters:', error);
            });
    }

    // 修改 populateDataTypeFilter 函数
    function populateDataTypeFilter(dataTypes) {
        // 首先清空现有的链接（除了 All）
        const allLinks = dataTypeFilter.querySelectorAll('.filter-link:not([data-type="All"])');
        allLinks.forEach(link => link.remove());

        dataTypes.forEach(item => {
            const link = document.createElement('a');
            link.href = '#';
            link.dataset.type = item.data_type;
            link.textContent = `${item.data_type} (${item.count})`;
            link.classList.add('filter-link');
            if (item.data_type === selectedDataType) {
                link.classList.add('active');
            }
            link.addEventListener('click', (e) => {
                e.preventDefault();
                selectedDataType = item.data_type;
                currentPage = 1;
                // 特别处理 All 的情况
                if (item.data_type === 'All') {
                    selectedDataType = 'All';
                    // 确保 UI 更新反映这个改变
                    updateActiveFilter(dataTypeFilter, link);
                }
                updateActiveFilter(dataTypeFilter, link);
                updateHiddenInputs();
                fetchResults();
            });
            dataTypeFilter.appendChild(link);
        });
    }

    // 修改 populateTaskFilter 函数
    function populateTaskFilter(tasks) {
        // 首先清空现有的链接（除了 All）
        const allLinks = taskFilter.querySelectorAll('.filter-link:not([data-task="All"])');
        allLinks.forEach(link => link.remove());

        tasks.forEach(item => {
            const link = document.createElement('a');
            link.href = '#';
            link.dataset.task = item.task;
            link.textContent = `${item.task} (${item.count})`;
            link.classList.add('filter-link');
            if (item.task === selectedTask) {
                link.classList.add('active');
            }
            link.addEventListener('click', (e) => {
                e.preventDefault();
                selectedTask = item.task;
                currentPage = 1;
                // 特别处理 All 的情况
                if (item.task === 'All') {
                    selectedTask = 'All';
                    // 确保 UI 更新反映这个改变
                    updateActiveFilter(taskFilter, link);
                }
                updateActiveFilter(taskFilter, link);
                updateHiddenInputs();
                fetchResults();
            });
            taskFilter.appendChild(link);
        });
    }

    // 添加对初始 "All" 链接的事件监听
    function initializeAllLinks() {
        // 为 Data Type 的 "All" 链接添加事件监听
        const dataTypeAllLink = dataTypeFilter.querySelector('a[data-type="All"]');
        if (dataTypeAllLink) {
            dataTypeAllLink.addEventListener('click', (e) => {
                e.preventDefault();
                selectedDataType = 'All';
                currentPage = 1;
                updateActiveFilter(dataTypeFilter, dataTypeAllLink);
                updateHiddenInputs();
                fetchResults();
            });
        }

        // 为 Task 的 "All" 链接添加事件监听
        const taskAllLink = taskFilter.querySelector('a[data-task="All"]');
        if (taskAllLink) {
            taskAllLink.addEventListener('click', (e) => {
                e.preventDefault();
                selectedTask = 'All';
                currentPage = 1;
                updateActiveFilter(taskFilter, taskAllLink);
                updateHiddenInputs();
                fetchResults();
            });
        }
    }

    // 修改 updateActiveFilter 函数
    function updateActiveFilter(container, activeLink) {
        // 移除所有链接的 active 类
        const links = container.querySelectorAll('.filter-link');
        links.forEach(link => {
            link.classList.remove('active');
        });
        
        // 添加 active 类到被点击的链接
        if (activeLink) {
            activeLink.classList.add('active');
        }
    }

    // 更新隐藏的输入字段
    function updateHiddenInputs() {
        document.getElementById('data_type').value = selectedDataType;
        document.getElementById('task').value = selectedTask;
    }

    // 处理表单提交
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        keywords = document.getElementById('keywords').value.trim();
        currentPage = 1;
        fetchResults();
    });

    // 处理上一页按钮
    prevPageBtn.addEventListener('click', function() {
        if (currentPage > 1) {
            currentPage--;
            fetchResults();
        }
    });

    // 处理下一页按钮
    nextPageBtn.addEventListener('click', function() {
        if (currentPage < totalPages) {
            currentPage++;
            fetchResults();
        }
    });

    // 处理页码选择器
    pageSelector.addEventListener('change', function() {
        currentPage = parseInt(this.value);
        fetchResults();
    });

    // 获取并显示搜索结果
    function fetchResults() {
        const params = new URLSearchParams({
            keywords: keywords,
            data_type: selectedDataType,
            task: selectedTask,
            page: currentPage
        });

        fetch(`${apiUrl}/api/search?${params.toString()}`)
            .then(response => response.json())
            .then(data => {
                displayResults(data.results);
                resultsCount.textContent = `Search Results: ${data.results_count} total items (${data.results.length} items on this page)`;
                totalPages = data.total_pages;
                populatePageSelector();
                updatePaginationButtons();
            })
            .catch(error => {
                console.error('Error fetching results:', error);
                resultsList.innerHTML = '<p>Error fetching results.</p>';
                resultsCount.textContent = 'Search Results: 0 total items (0 items on this page)';
            });
    }

    // 显示搜索结果
    function displayResults(results) {
        if (results.length > 0) {
            resultsList.innerHTML = '';
            results.forEach(result => {
                const item = document.createElement('div');
                item.className = 'result-item';

                // 构建 arXiv ID 和标题
                let title = '';
                if (result.arxiv_id) {
                    title = `<h4>${result.title || 'Untitled'}</h4>`;
                } else {
                    title = `<h4>${result.title || 'Untitled'}</h4>`;
                }

                // 处理Dataset显示逻辑：如果有Dataset Entity显示Dataset Entity，否则显示Dataset Name
                let datasetInfo = '';
                const hostname = window.location.hostname;
                
                if (result.dataset_entity) {
                    // Always use baseUrl for internal navigation
                    const datasetUrl = `${baseUrl}/dataset/${encodeURIComponent(result.dataset_entity)}`;
                    datasetInfo = `<p><strong>Dataset Entity:</strong> <a href="${datasetUrl}">${result.dataset_entity}</a></p>`;
                } else if (result.dataset_name) {
                    datasetInfo = `<p><strong>Dataset Name:</strong> ${result.dataset_name}`;
                    if (result.homepage) {
                        datasetInfo += ` <a href="${result.homepage}" target="_blank">[Homepage]</a>`;
                    }
                    datasetInfo += `</p>`;
                } else {
                    datasetInfo = `<p><strong>Dataset Name:</strong> N/A</p>`;
                }

                // 组合所有信息
                let resultHtml = `${title}${datasetInfo}`;
                
                // 只显示有值的字段
                if (result.arxiv_id) {
                    resultHtml += `<p><strong>arXiv ID:</strong> <a href="https://arxiv.org/abs/${result.arxiv_id}" target="_blank">${result.arxiv_id}</a></p>`;
                }
                
                if (result.dataset_url) {
                    resultHtml += `<p><strong>Dataset URL:</strong> <a href="${result.dataset_url}" target="_blank">${result.dataset_url}</a></p>`;
                }
                
                if (result.task) {
                    resultHtml += `<p><strong>Task:</strong> ${result.task}</p>`;
                }
                
                if (result.data_type) {
                    resultHtml += `<p><strong>Data Type:</strong> ${result.data_type}</p>`;
                }
                
                if (result.scale) {
                    resultHtml += `<p><strong>Data Scale:</strong> ${result.scale}</p>`;
                }
                
                if (result.location) {
                    resultHtml += `<p><strong>Location:</strong> ${result.location}</p>`;
                }
                
                if (result.dataset_summary) {
                    resultHtml += `<p><strong>Summary:</strong> ${result.dataset_summary}</p>`;
                }
                
                if (result.other_info) {
                    resultHtml += `<p><strong>Other Information:</strong> ${result.other_info}</p>`;
                }
                
                item.innerHTML = resultHtml;
                resultsList.appendChild(item);
            });
        } else {
            resultsList.innerHTML = '<p>No results found.</p>';
        }
    }

    // 填充页码选择器
    function populatePageSelector() {
        pageSelector.innerHTML = '';
        for (let i = 1; i <= totalPages; i++) {
            const option = document.createElement('option');
            option.value = i;
            option.textContent = `Page ${i} of ${totalPages}`;
            if (i === currentPage) {
                option.selected = true;
            }
            pageSelector.appendChild(option);
        }
    }

    // 更新分页按钮的状态
    function updatePaginationButtons() {
        prevPageBtn.disabled = currentPage <= 1;
        nextPageBtn.disabled = currentPage >= totalPages;
    }

    // 初始化加载结果
    fetchResults();
});

