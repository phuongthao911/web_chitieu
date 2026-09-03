let transactions = [];
let expenseChart = null;
let incomeChart = null;
let trendChart = null;
let dbCategories = []; // Loaded from API

const form = document.getElementById("transaction-form");
const amountInput = document.getElementById("amount");
const typeInput = document.getElementById("type");
const categoryInput = document.getElementById("category");
const walletInput = document.getElementById("wallet");
const noteInput = document.getElementById("note");
const tbody = document.getElementById("transaction-list");
const totalIncomeEl = document.getElementById("total-income");
const totalExpenseEl = document.getElementById("total-expense");
const balanceEl = document.getElementById("balance");
const chartCanvas = document.getElementById("expenseChart");
const incomeChartCanvas = document.getElementById("incomeChart");
const historyTypeFilter = document.getElementById("history-type-filter");
const historyMonthFilter = document.getElementById("history-month-filter");
const historyWalletFilter = document.getElementById("history-wallet-filter");
const historySearch = document.getElementById("history-search");
const searchBtn = document.getElementById("search-btn");

const WALLET_ID_MAP = {
    "Tiền mặt": "cash",
    "Tài khoản tiết kiệm": "savings",
    "TK ngân hàng": "bank"
};
const submitBtn = document.getElementById("submit-btn");
const submitBtnLabel = document.getElementById("submit-btn-label");
const cancelEditBtn = document.getElementById("cancel-edit-btn");
const destinationWalletInput = document.getElementById("destination-wallet");
const destinationWalletGroup = document.getElementById("destination-wallet-group");
const categoryGroup = document.getElementById("category-group");

// Recurring UI selectors
const recurringForm = document.getElementById("recurring-form");
const recurringTypeSelect = document.getElementById("recurring-type");
const recurringAmountInput = document.getElementById("recurring-amount");
const recurringCategorySelect = document.getElementById("recurring-category");
const recurringWalletSelect = document.getElementById("recurring-wallet");
const recurringDestWalletSelect = document.getElementById("recurring-destination-wallet");
const recurringDestWalletGroup = document.getElementById("rec-destination-wallet-group");
const recurringCategoryGroup = document.getElementById("rec-category-group");
const recurringDayInput = document.getElementById("recurring-day");
const recurringNoteInput = document.getElementById("recurring-note");
const recurringListTbody = document.getElementById("recurring-list");

// Category UI selectors
const categoryForm = document.getElementById("category-form");
const categoryNameInput = document.getElementById("category-name");
const categoryTypeInput = document.getElementById("category-type");
const categorySubmitBtn = document.getElementById("category-submit-btn");
const categoryCancelBtn = document.getElementById("category-cancel-btn");
const categoryListTbody = document.getElementById("category-list");
const categoryFormTitle = document.getElementById("category-form-title");
const trendChartCanvas = document.getElementById("trendChart");

const budgetMonthFilter = document.getElementById("budget-month-filter");
const budgetItemsContainer = document.getElementById("budget-items-container");
const budgetTotalSummary = document.getElementById("budget-total-summary");

let editingCategoryId = null;

const CATEGORY_COLOR_PALETTE = [
    "#f2789e", "#eb9c5c", "#6fc79a", "#8ec9e0",
    "#c99ee0", "#f3b95f", "#5cb99a", "#f39fc0",
    "#9a8cf0", "#e8607f", "#6ec6c4", "#f0a868"
];

const categoryColorMap = {};
let nextPaletteIndex = 0;

function getColorForCategory(category) {
    if (!categoryColorMap[category]) {
        categoryColorMap[category] = CATEGORY_COLOR_PALETTE[nextPaletteIndex % CATEGORY_COLOR_PALETTE.length];
        nextPaletteIndex += 1;
    }

    return categoryColorMap[category];
}

let editingId = null;

function populateCategoryOptions(type, selectedCategory) {
    const options = dbCategories.filter(cat => cat.type === type);

    categoryInput.innerHTML = "";

    options.forEach(cat => {
        const option = document.createElement("option");
        option.value = cat.name;
        option.textContent = (type === "income" ? "💰 " : "💸 ") + cat.name;
        categoryInput.appendChild(option);
    });

    const values = options.map(option => option.name);

    if (selectedCategory && values.includes(selectedCategory)) {
        categoryInput.value = selectedCategory;
    } else {
        categoryInput.selectedIndex = 0;
    }
}

function getCurrentMonthValue(date = new Date()) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    return `${year}-${month}`;
}

historyMonthFilter.value = getCurrentMonthValue();

function formatMoney(number) {
    return Number(number).toLocaleString("en-US") + " VND";
}

function parseAmount(value) {
    const rawNumber = Number(String(value).replace(/,/g, "").trim());
    return rawNumber * 1000;
}

function formatAmountInput(value) {
    const cleaned = String(value).replace(/[^\d]/g, "");

    if (!cleaned) {
        return "";
    }

    return Number(cleaned).toLocaleString("en-US");
}

function resetAmountInput() {
    amountInput.value = "";
}

function updateSummary() {
    const income = transactions
        .filter(transaction => transaction.type === "Income")
        .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

    const expense = transactions
        .filter(transaction => transaction.type === "Expense")
        .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

    totalIncomeEl.textContent = formatMoney(income);
    totalExpenseEl.textContent = formatMoney(expense);
    balanceEl.textContent = formatMoney(income - expense);

    updateWalletSummary();
}

function updateWalletSummary() {
    Object.entries(WALLET_ID_MAP).forEach(([walletName, idPrefix]) => {
        // Transactions outgoing or related to this wallet
        const walletTransactions = transactions.filter(transaction => transaction.wallet === walletName);
        
        // Incoming transfers specifically to this wallet
        const incomingTransfers = transactions.filter(transaction => transaction.type === "Transfer" && transaction.destination_wallet === walletName);

        const income = walletTransactions
            .filter(transaction => transaction.type === "Income")
            .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

        const expense = walletTransactions
            .filter(transaction => transaction.type === "Expense")
            .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

        const outgoingTransfersSum = walletTransactions
            .filter(transaction => transaction.type === "Transfer")
            .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

        const incomingTransfersSum = incomingTransfers
            .reduce((sum, transaction) => sum + Number(transaction.amount), 0);

        // Balance = Income + Incoming Transfers - Expense - Outgoing Transfers
        const balanceVal = income + incomingTransfersSum - expense - outgoingTransfersSum;

        const incomeEl = document.getElementById(`wallet-${idPrefix}-income`);
        const expenseEl = document.getElementById(`wallet-${idPrefix}-expense`);
        const walletBalanceEl = document.getElementById(`wallet-${idPrefix}-balance`);

        if (incomeEl) incomeEl.textContent = formatMoney(income);
        if (expenseEl) expenseEl.textContent = formatMoney(expense);
        if (walletBalanceEl) walletBalanceEl.textContent = formatMoney(balanceVal);
    });
}

function updateChart() {
    const visibleTransactions = getVisibleTransactions();

    const incomeByCategory = visibleTransactions
        .filter(transaction => transaction.type === "Income")
        .reduce((accumulator, transaction) => {
            accumulator[transaction.category] = (accumulator[transaction.category] || 0) + Number(transaction.amount);
            return accumulator;
        }, {});

    const expenseByCategory = visibleTransactions
        .filter(transaction => transaction.type === "Expense")
        .reduce((accumulator, transaction) => {
            accumulator[transaction.category] = (accumulator[transaction.category] || 0) + Number(transaction.amount);
            return accumulator;
        }, {});

    if (incomeChart) {
        const incomeLabels = Object.keys(incomeByCategory);
        incomeChart.data.labels = incomeLabels;
        incomeChart.data.datasets[0].data = Object.values(incomeByCategory);
        incomeChart.data.datasets[0].backgroundColor = incomeLabels.map(getColorForCategory);
        incomeChart.update();
    }

    if (expenseChart) {
        const expenseLabels = Object.keys(expenseByCategory);
        expenseChart.data.labels = expenseLabels;
        expenseChart.data.datasets[0].data = Object.values(expenseByCategory);
        expenseChart.data.datasets[0].backgroundColor = expenseLabels.map(getColorForCategory);
        expenseChart.update();
    }

    updateTrendChart(visibleTransactions);
}

function updateTrendChart(visibleTransactions) {
    if (!trendChart) return;

    // Group transactions by date (YYYY-MM-DD)
    const grouped = {};
    visibleTransactions.forEach(t => {
        const dateStr = t.created_at ? t.created_at.split(" ")[0] : "";
        if (!dateStr) return;
        if (!grouped[dateStr]) {
            grouped[dateStr] = { income: 0, expense: 0 };
        }
        if (t.type === "Income") {
            grouped[dateStr].income += Number(t.amount);
        } else if (t.type === "Expense") {
            grouped[dateStr].expense += Number(t.amount);
        }
    });

    // Sort dates chronologically
    const sortedDates = Object.keys(grouped).sort();

    const incomeData = [];
    const expenseData = [];

    sortedDates.forEach(date => {
        incomeData.push(grouped[date].income);
        expenseData.push(grouped[date].expense);
    });

    trendChart.data.labels = sortedDates;
    trendChart.data.datasets[0].data = incomeData;
    trendChart.data.datasets[1].data = expenseData;
    trendChart.update();
}

function getVisibleTransactions() {
    const selectedType = historyTypeFilter.value;
    const selectedMonth = historyMonthFilter.value;
    const selectedWallet = historyWalletFilter.value;
    const searchText = historySearch ? historySearch.value.trim().toLowerCase() : "";

    return transactions.filter(transaction => {
        const matchesType = selectedType === "all" || transaction.type === selectedType;
        const matchesMonth = !selectedMonth || transaction.created_at.startsWith(selectedMonth);
        const matchesWallet = selectedWallet === "all" || transaction.wallet === selectedWallet;

        let matchesSearch = true;
        if (searchText) {
            const matchesNote = transaction.note && String(transaction.note).toLowerCase().includes(searchText);
            const matchesAmount = String(transaction.amount).includes(searchText);
            const matchesCategory = transaction.category && String(transaction.category).toLowerCase().includes(searchText);
            matchesSearch = matchesNote || matchesAmount || matchesCategory;
        }

        return matchesType && matchesMonth && matchesWallet && matchesSearch;
    });
}

function renderTable() {
    const visibleTransactions = getVisibleTransactions();

    tbody.innerHTML = "";

    if (visibleTransactions.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");

        cell.colSpan = 7;
        cell.textContent = "No transactions found.";
        row.appendChild(cell);
        tbody.appendChild(row);
        updateSummary();
        updateChart();
        return;
    }

    visibleTransactions.forEach(transaction => {
        const row = document.createElement("tr");

        const typeCell = document.createElement("td");
        typeCell.textContent = transaction.type === "Transfer" ? "Transfer 🔄" : transaction.type;

        const categoryCell = document.createElement("td");
        categoryCell.textContent = transaction.category;

        const walletCell = document.createElement("td");
        if (transaction.type === "Transfer") {
            const fromWallet = transaction.wallet === "TK ngân hàng" ? "Tài khoản ngân hàng" : transaction.wallet;
            const toWallet = transaction.destination_wallet === "TK ngân hàng" ? "Tài khoản ngân hàng" : transaction.destination_wallet;
            walletCell.textContent = `${fromWallet} ➡️ ${toWallet}`;
        } else {
            walletCell.textContent = transaction.wallet === "TK ngân hàng" ? "Tài khoản ngân hàng" : transaction.wallet;
        }

        const amountCell = document.createElement("td");
        amountCell.textContent = formatMoney(transaction.amount);

        const dateCell = document.createElement("td");
        dateCell.textContent = transaction.created_at;

        const noteCell = document.createElement("td");
        noteCell.textContent = transaction.note;

        const actionCell = document.createElement("td");

        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.innerHTML = '<i class="fa-solid fa-pen"></i> Edit';
        editButton.classList.add("edit-btn");
        editButton.addEventListener("click", () => enterEditMode(transaction));
        actionCell.appendChild(editButton);

        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.innerHTML = '<i class="fa-solid fa-trash"></i> Delete';
        deleteButton.classList.add("delete-btn");
        deleteButton.addEventListener("click", () => deleteTransaction(transaction.id));
        actionCell.appendChild(deleteButton);

        if (transaction.id === editingId) {
            row.classList.add("editing-row");
        }

        row.appendChild(typeCell);
        row.appendChild(categoryCell);
        row.appendChild(walletCell);
        row.appendChild(amountCell);
        row.appendChild(dateCell);
        row.appendChild(noteCell);
        row.appendChild(actionCell);

        tbody.appendChild(row);
    });

    updateSummary();
    updateChart();
}

async function loadTransactions() {
    const response = await fetch("/api/transactions");

    if (!response.ok) {
        throw new Error("Failed to load transactions.");
    }

    transactions = await response.json();
    await loadCategories();
    if (budgetMonthFilter) {
        budgetMonthFilter.value = getCurrentMonthValue();
    }
    await loadBudgets();
    renderTable();
}

async function loadBudgets() {
    if (!budgetMonthFilter) return;
    const month = budgetMonthFilter.value;
    const response = await fetch(`/api/budgets?month=${month}`);
    if (!response.ok) {
        console.error("Failed to load budgets");
        return;
    }
    const budgets = await response.json();
    renderBudgets(budgets);
}

function renderBudgets(budgets) {
    if (!budgetItemsContainer) return;
    budgetItemsContainer.innerHTML = "";

    if (budgetTotalSummary) {
        budgetTotalSummary.innerHTML = "";
    }

    if (budgets.length === 0) {
        budgetItemsContainer.innerHTML = "<p>Vui lòng thêm danh mục chi tiêu trước.</p>";
        if (budgetTotalSummary) {
            budgetTotalSummary.style.display = "none";
        }
        return;
    }

    // Calculate overall budget totals
    let totalLimit = 0;
    let totalSpending = 0;
    budgets.forEach(b => {
        totalLimit += (b.amount_limit || 0);
        totalSpending += (b.actual_spending || 0);
    });

    if (budgetTotalSummary) {
        budgetTotalSummary.style.display = "block";
        const totalPercent = totalLimit > 0 ? (totalSpending / totalLimit) * 100 : 0;
        let totalStatusClass = "status-safe";
        if (totalPercent >= 100) {
            totalStatusClass = "status-danger";
        } else if (totalPercent >= 80) {
            totalStatusClass = "status-warning";
        }

        const remaining = totalLimit - totalSpending;
        let remainingHtml = "";
        if (totalLimit > 0) {
            if (remaining >= 0) {
                remainingHtml = `<span class="budget-total-stat-item positive"><i class="fa-solid fa-coins"></i> Còn lại: <strong>${formatMoney(remaining)}</strong></span>`;
            } else {
                remainingHtml = `<span class="budget-total-stat-item negative"><i class="fa-solid fa-circle-exclamation"></i> Vượt mức: <strong>${formatMoney(Math.abs(remaining))}</strong></span>`;
            }
        }

        budgetTotalSummary.className = `budget-total-card ${totalStatusClass}`;
        budgetTotalSummary.innerHTML = `
            <div class="budget-total-header">
                <div class="budget-total-title-wrap">
                    <span class="budget-total-badge"><i class="fa-solid fa-chart-pie"></i> Tổng quan ngân sách</span>
                    <span class="budget-total-percent">${totalLimit > 0 ? totalPercent.toFixed(1) + '%' : 'Chưa đặt hạn mức'}</span>
                </div>
                <div class="budget-total-amounts">
                    <span class="budget-total-spent">${formatMoney(totalSpending)}</span>
                    <span class="budget-total-divider">/</span>
                    <span class="budget-total-limit">${totalLimit > 0 ? formatMoney(totalLimit) : "Chưa đặt"}</span>
                </div>
            </div>
            <div class="budget-progress-bg budget-total-progress-bg">
                <div class="budget-progress-bar" style="width: ${Math.min(totalPercent, 100)}%"></div>
            </div>
            <div class="budget-total-footer">
                <span class="budget-total-stat-item"><i class="fa-solid fa-layer-group"></i> ${budgets.length} danh mục</span>
                ${remainingHtml}
            </div>
        `;
    }

    budgets.forEach(b => {
        const percent = b.amount_limit > 0 ? (b.actual_spending / b.amount_limit) * 100 : 0;
        
        let statusClass = "status-safe";
        if (percent >= 100) {
            statusClass = "status-danger";
        } else if (percent >= 80) {
            statusClass = "status-warning";
        }

        const itemDiv = document.createElement("div");
        itemDiv.className = `budget-card ${statusClass}`;
        
        itemDiv.innerHTML = `
            <div class="budget-info">
                <span class="budget-cat-name">💸 ${b.category_name}</span>
                <span class="budget-ratio">${formatMoney(b.actual_spending)} / <span class="limit-label" id="limit-text-${b.category_name}">${b.amount_limit > 0 ? formatMoney(b.amount_limit) : "Chưa đặt"}</span></span>
            </div>
            <div class="budget-progress-bg">
                <div class="budget-progress-bar" style="width: ${Math.min(percent, 100)}%"></div>
            </div>
            <div class="budget-actions">
                <input type="text" placeholder="Đặt hạn mức..." id="input-limit-${b.category_name}" class="budget-input-field" value="${b.amount_limit > 0 ? b.amount_limit / 1000 : ""}">
                <button type="button" class="budget-save-btn" onclick="saveCategoryBudget('${b.category_name}')">
                    <i class="fa-solid fa-floppy-disk"></i>
                </button>
            </div>
            ${percent >= 100 ? '<span class="budget-warn-badge"><i class="fa-solid fa-triangle-exclamation"></i> ĐÃ VƯỢT HẠN MỨC!</span>' : percent >= 80 ? '<span class="budget-warn-badge warning"><i class="fa-solid fa-circle-exclamation"></i> Sắp vượt hạn mức!</span>' : ''}
        `;
        budgetItemsContainer.appendChild(itemDiv);
    });
}

async function saveCategoryBudget(categoryName) {
    const inputEl = document.getElementById(`input-limit-${categoryName}`);
    if (!inputEl) return;
    const value = inputEl.value.replace(/,/g, "").trim();
    if (!value || isNaN(value)) {
        alert("Vui lòng nhập hạn mức hợp lệ.");
        return;
    }
    const limitAmount = Number(value) * 1000;
    const month = budgetMonthFilter.value;

    try {
        const response = await fetch("/api/budgets", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                category_name: categoryName,
                month: month,
                amount_limit: limitAmount
            })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "Không thể lưu ngân sách");
        }

        await loadBudgets();
    } catch (e) {
        alert(e.message);
    }
}

async function loadCategories() {
    const response = await fetch("/api/categories");
    if (!response.ok) {
        throw new Error("Failed to load categories.");
    }
    dbCategories = await response.json();
    populateCategoryOptions(typeInput.value);
    populateRecurringCategoryOptions(recurringTypeSelect ? recurringTypeSelect.value.toLowerCase() : "expense");
    renderCategoryList();
}

function populateRecurringCategoryOptions(type) {
    if (!recurringCategorySelect) return;
    const options = dbCategories.filter(cat => cat.type === type);
    recurringCategorySelect.innerHTML = "";
    options.forEach(cat => {
        const option = document.createElement("option");
        option.value = cat.name;
        option.textContent = cat.name;
        recurringCategorySelect.appendChild(option);
    });
}

function renderCategoryList() {
    if (!categoryListTbody) return;
    categoryListTbody.innerHTML = "";
    dbCategories.forEach(cat => {
        const row = document.createElement("tr");

        const nameCell = document.createElement("td");
        nameCell.textContent = cat.name;

        const typeCell = document.createElement("td");
        typeCell.textContent = cat.type === "income" ? "Income" : "Expense";

        const actionCell = document.createElement("td");

        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "edit-btn";
        editBtn.innerHTML = '<i class="fa-solid fa-pen"></i>';
        editBtn.addEventListener("click", () => enterCategoryEditMode(cat));

        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "delete-btn";
        deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        deleteBtn.addEventListener("click", () => deleteCategory(cat.id));

        actionCell.appendChild(editBtn);
        actionCell.appendChild(deleteBtn);

        row.appendChild(nameCell);
        row.appendChild(typeCell);
        row.appendChild(actionCell);

        categoryListTbody.appendChild(row);
    });
}

function enterCategoryEditMode(cat) {
    editingCategoryId = cat.id;
    categoryNameInput.value = cat.name;
    categoryTypeInput.value = cat.type;
    categorySubmitBtn.innerHTML = '<i class="fa-solid fa-check"></i> Update Category';
    categoryCancelBtn.hidden = false;
    categoryFormTitle.textContent = "Edit Category";
}

function exitCategoryEditMode() {
    editingCategoryId = null;
    categoryForm.reset();
    categorySubmitBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Save Category';
    categoryCancelBtn.hidden = true;
    categoryFormTitle.textContent = "Add Category";
}

async function deleteCategory(id) {
    if (!confirm("Are you sure you want to delete this category?")) return;
    const response = await fetch(`/api/categories/${id}`, { method: "DELETE" });
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        alert(error.detail || "Failed to delete category.");
        return;
    }
    await loadCategories();
}

async function createTransaction(payload) {
    const response = await fetch("/api/transactions", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || "Failed to save transaction.");
    }

    return response.json();
}

async function updateTransaction(id, payload) {
    const response = await fetch(`/api/transactions/${id}`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || "Failed to update transaction.");
    }

    return response.json();
}

function enterEditMode(transaction) {
    editingId = transaction.id;

    const type = transaction.type.toLowerCase();
    typeInput.value = type;
    
    if (type === "transfer") {
        if (categoryGroup) categoryGroup.style.display = "none";
        if (destinationWalletGroup) destinationWalletGroup.style.display = "block";
        if (destinationWalletInput) destinationWalletInput.value = transaction.destination_wallet || "";
    } else {
        if (categoryGroup) categoryGroup.style.display = "block";
        if (destinationWalletGroup) destinationWalletGroup.style.display = "none";
        populateCategoryOptions(type, transaction.category);
    }
    
    walletInput.value = transaction.wallet;
    noteInput.value = transaction.note === "-" ? "" : transaction.note;
    amountInput.value = formatAmountInput(String(transaction.amount / 1000));

    submitBtnLabel.textContent = "Update Transaction";
    cancelEditBtn.hidden = false;

    renderTable();
    form.scrollIntoView({ behavior: "smooth", block: "start" });
}

function exitEditMode() {
    editingId = null;
    form.reset();
    resetAmountInput();
    if (categoryGroup) categoryGroup.style.display = "block";
    if (destinationWalletGroup) destinationWalletGroup.style.display = "none";
    populateCategoryOptions(typeInput.value);

    submitBtnLabel.textContent = "Add Transaction";
    cancelEditBtn.hidden = true;

    renderTable();
}

async function deleteTransaction(id) {
    const response = await fetch(`/api/transactions/${id}`, {
        method: "DELETE"
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || "Failed to delete transaction.");
    }

    transactions = transactions.filter(transaction => transaction.id !== id);
    renderTable();
}

form.addEventListener("submit", async event => {
    event.preventDefault();

    const amount = parseAmount(amountInput.value);

    if (!amount || Number.isNaN(amount)) {
        return;
    }

    const payload = {
        type: typeInput.value,
        category: typeInput.value === "transfer" ? "Chuyển ví" : categoryInput.value,
        wallet: walletInput.value,
        destination_wallet: typeInput.value === "transfer" ? destinationWalletInput.value : null,
        amount,
        note: noteInput.value.trim()
    };

    try {
        if (editingId) {
            const updatedTransaction = await updateTransaction(editingId, payload);
            const index = transactions.findIndex(transaction => transaction.id === editingId);

            if (index !== -1) {
                transactions[index] = updatedTransaction;
            }

            exitEditMode();
        } else {
            const savedTransaction = await createTransaction(payload);

            transactions.unshift(savedTransaction);
            form.reset();
            resetAmountInput();
            populateCategoryOptions(typeInput.value);
            renderTable();
        }
    } catch (error) {
        console.error(error);
        alert(error.message);
    }
});

cancelEditBtn.addEventListener("click", () => {
    exitEditMode();
});

amountInput.addEventListener("focus", () => {
    amountInput.select();
});

amountInput.addEventListener("input", () => {
    amountInput.value = formatAmountInput(amountInput.value);
});

typeInput.addEventListener("change", () => {
    const type = typeInput.value;
    if (type === "transfer") {
        if (categoryGroup) categoryGroup.style.display = "none";
        if (destinationWalletGroup) destinationWalletGroup.style.display = "block";
    } else {
        if (categoryGroup) categoryGroup.style.display = "block";
        if (destinationWalletGroup) destinationWalletGroup.style.display = "none";
        populateCategoryOptions(type);
    }
});

historyTypeFilter.addEventListener("change", renderTable);
historyMonthFilter.addEventListener("change", renderTable);
historyWalletFilter.addEventListener("change", renderTable);
if (budgetMonthFilter) {
    budgetMonthFilter.addEventListener("change", loadBudgets);
}
window.saveCategoryBudget = saveCategoryBudget;

if (historySearch) {
    historySearch.addEventListener("input", renderTable);
    historySearch.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            renderTable();
        }
    });
}
if (searchBtn) {
    searchBtn.addEventListener("click", renderTable);
}

// Category form listeners
if (categoryForm) {
    categoryForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const name = categoryNameInput.value.trim();
        const type = categoryTypeInput.value;
        if (!name) return;

        const payload = { name, type };
        try {
            if (editingCategoryId) {
                // Update
                const response = await fetch(`/api/categories/${editingCategoryId}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                if (!response.ok) {
                    const err = await response.json().catch(() => ({}));
                    throw new Error(err.detail || "Failed to update category.");
                }
            } else {
                // Create
                const response = await fetch("/api/categories", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                if (!response.ok) {
                    const err = await response.json().catch(() => ({}));
                    throw new Error(err.detail || "Failed to create category.");
                }
            }
            exitCategoryEditMode();
            await loadCategories();
            renderTable();
        } catch (error) {
            console.error(error);
            alert(error.message);
        }
    });
}

if (categoryCancelBtn) {
    categoryCancelBtn.addEventListener("click", exitCategoryEditMode);
}

resetAmountInput();
populateCategoryOptions(typeInput.value);

const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            position: "right",
            labels: {
                usePointStyle: true,
                pointStyle: "circle",
                boxWidth: 10,
                padding: 14,
                color: "#6e3a50",
                font: {
                    size: 13
                }
            }
        }
    }
};

expenseChart = new Chart(chartCanvas, {
    type: "pie",
    data: {
        labels: [],
        datasets: [{
            data: [],
            backgroundColor: [],
            borderColor: "#fffbfc",
            borderWidth: 2
        }]
    },
    options: chartOptions
});

incomeChart = new Chart(incomeChartCanvas, {
    type: "pie",
    data: {
        labels: [],
        datasets: [{
            data: [],
            backgroundColor: [],
            borderColor: "#fffbfc",
            borderWidth: 2
        }]
    },
    options: chartOptions
});

if (trendChartCanvas) {
    trendChart = new Chart(trendChartCanvas, {
        type: "line",
        data: {
            labels: [],
            datasets: [
                {
                    label: "Thu nhập (Income)",
                    data: [],
                    borderColor: "#6fc79a",
                    backgroundColor: "rgba(111, 199, 154, 0.1)",
                    borderWidth: 3,
                    fill: true,
                    tension: 0.3
                },
                {
                    label: "Chi tiêu (Expense)",
                    data: [],
                    borderColor: "#ea6a8c",
                    backgroundColor: "rgba(234, 106, 140, 0.1)",
                    borderWidth: 3,
                    fill: true,
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "top",
                    labels: {
                        color: "#6e3a50",
                        font: { size: 13, weight: "bold" }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: "#9a6b80" }
                },
                y: {
                    grid: { color: "rgba(216, 92, 133, 0.1)" },
                    ticks: { color: "#9a6b80" }
                }
            }
        }
    });
}

loadTransactions().then(() => {
    loadRecurring();
}).catch(error => {
    console.error(error);
    alert(error.message);
});

async function loadRecurring() {
    const response = await fetch("/api/recurring");
    if (!response.ok) return;
    const items = await response.json();
    renderRecurringList(items);
}

function renderRecurringList(items) {
    if (!recurringListTbody) return;
    recurringListTbody.innerHTML = "";
    items.forEach(r => {
        const row = document.createElement("tr");

        const typeCell = document.createElement("td");
        typeCell.textContent = r.type;

        const amountCell = document.createElement("td");
        amountCell.textContent = formatMoney(r.amount);

        const catNoteCell = document.createElement("td");
        catNoteCell.textContent = `${r.category} | ${r.note}`;

        const walletCell = document.createElement("td");
        if (r.type === "Transfer") {
            walletCell.textContent = `${r.wallet} ➡️ ${r.destination_wallet}`;
        } else {
            walletCell.textContent = r.wallet;
        }

        const dayCell = document.createElement("td");
        dayCell.textContent = `Ngày ${r.day_of_month}`;

        const runCell = document.createElement("td");
        runCell.textContent = r.last_executed_month || "Chưa chạy";

        const actionCell = document.createElement("td");
        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "delete-btn";
        deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        deleteBtn.addEventListener("click", async () => {
            if (!confirm("Xóa cấu hình định kỳ này?")) return;
            const res = await fetch(`/api/recurring/${r.id}`, { method: "DELETE" });
            if (res.ok) {
                loadRecurring();
            }
        });
        actionCell.appendChild(deleteBtn);

        row.appendChild(typeCell);
        row.appendChild(amountCell);
        row.appendChild(catNoteCell);
        row.appendChild(walletCell);
        row.appendChild(dayCell);
        row.appendChild(runCell);
        row.appendChild(actionCell);

        recurringListTbody.appendChild(row);
    });
}

// Bind recurring event listeners
if (recurringTypeSelect) {
    recurringTypeSelect.addEventListener("change", () => {
        const type = recurringTypeSelect.value.toLowerCase();
        if (type === "transfer") {
            if (recurringCategoryGroup) recurringCategoryGroup.style.display = "none";
            if (recurringDestWalletGroup) recurringDestWalletGroup.style.display = "block";
        } else {
            if (recurringCategoryGroup) recurringCategoryGroup.style.display = "block";
            if (recurringDestWalletGroup) recurringDestWalletGroup.style.display = "none";
            populateRecurringCategoryOptions(type);
        }
    });
}

if (recurringAmountInput) {
    recurringAmountInput.addEventListener("input", () => {
        recurringAmountInput.value = formatAmountInput(recurringAmountInput.value);
    });
}

if (recurringForm) {
    recurringForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const amount = parseAmount(recurringAmountInput.value);
        if (!amount || isNaN(amount)) return;

        const payload = {
            type: recurringTypeSelect.value,
            amount: amount,
            category: recurringTypeSelect.value === "Transfer" ? "Chuyển ví" : recurringCategorySelect.value,
            wallet: recurringWalletSelect.value,
            destination_wallet: recurringTypeSelect.value === "Transfer" ? recurringDestWalletSelect.value : null,
            day_of_month: parseInt(recurringDayInput.value),
            note: recurringNoteInput.value.trim()
        };

        try {
            const res = await fetch("/api/recurring", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || "Không thể thêm cấu hình");
            }

            recurringForm.reset();
            if (recurringCategoryGroup) recurringCategoryGroup.style.display = "block";
            if (recurringDestWalletGroup) recurringDestWalletGroup.style.display = "none";
            populateRecurringCategoryOptions(recurringTypeSelect.value.toLowerCase());
            await loadRecurring();
            await loadTransactions();
        } catch (error) {
            alert(error.message);
        }
    });
}

// Backup Dropdown Logic
const backupBtn = document.getElementById("backup-btn");
const backupDropdown = document.getElementById("backup-dropdown");

if (backupBtn && backupDropdown) {
    backupBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        backupDropdown.classList.toggle("show");
    });

    document.addEventListener("click", (e) => {
        if (!backupBtn.contains(e.target) && !backupDropdown.contains(e.target)) {
            backupDropdown.classList.remove("show");
        }
    });
}

// Top Tabs switching logic
document.querySelectorAll(".top-tabs-bar .tab-btn").forEach(button => {
    button.addEventListener("click", () => {
        // Remove active class from all tab buttons
        document.querySelectorAll(".top-tabs-bar .tab-btn").forEach(btn => btn.classList.remove("active"));
        // Add active class to clicked button
        button.classList.add("active");

        // Hide all tab panes
        document.querySelectorAll(".tab-pane").forEach(pane => pane.classList.remove("active"));
        // Show corresponding tab pane
        const targetTabId = button.getAttribute("data-tab");
        const targetPane = document.getElementById(targetTabId);
        if (targetPane) {
            targetPane.classList.add("active");
        }
    });
});

// JSON Import logic
const importJsonInput = document.getElementById("import-json-file");
if (importJsonInput) {
    importJsonInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = async (event) => {
            try {
                const data = JSON.parse(event.target.result);
                
                let itemCount = 0;
                if (Array.isArray(data)) {
                    itemCount = data.length;
                } else if (data && typeof data === "object") {
                    itemCount = (data.transactions?.length || 0) + (data.categories?.length || 0) + (data.budgets?.length || 0) + (data.recurring?.length || 0);
                }

                // Show confirming prompt
                if (!confirm(`Bạn có chắc chắn muốn nhập dữ liệu backup (${itemCount} mục) từ file JSON này? Dữ liệu hiện tại sẽ được bảo lưu.`)) {
                    importJsonInput.value = "";
                    return;
                }

                const response = await fetch("/api/backup/import", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data)
                });

                if (!response.ok) {
                    const err = await response.json().catch(() => ({}));
                    throw new Error(err.detail || "Nhập file thất bại.");
                }

                const result = await response.json();
                alert(result.message || "Nhập dữ liệu thành công!");
                
                // Reload transactions, categories, budgets, and recurring settings across all tabs
                await loadTransactions();
                if (typeof loadCategories === "function") {
                    await loadCategories();
                }
                if (typeof loadBudgets === "function") {
                    await loadBudgets();
                }
                if (typeof loadRecurring === "function") {
                    await loadRecurring();
                }

                // Close backup dropdown
                if (backupDropdown) {
                    backupDropdown.classList.remove("show");
                }

            } catch (error) {
                alert("Lỗi: " + error.message);
            } finally {
                importJsonInput.value = "";
            }
        };
        reader.readAsText(file);
    });
}

// CSV Import logic
const importCsvInput = document.getElementById("import-csv-file");
if (importCsvInput) {
    importCsvInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        if (!confirm(`Bạn có chắc chắn muốn nhập dữ liệu từ file CSV "${file.name}"? Dữ liệu hiện tại sẽ được bảo lưu.`)) {
            importCsvInput.value = "";
            return;
        }

        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch("/api/backup/import-csv", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || "Nhập file CSV thất bại.");
            }

            const result = await response.json();
            alert(result.message || "Nhập file CSV thành công!");

            // Reload all data
            await loadTransactions();
            if (typeof loadCategories === "function") await loadCategories();
            if (typeof loadBudgets === "function") await loadBudgets();
            if (typeof loadRecurring === "function") await loadRecurring();

            if (backupDropdown) backupDropdown.classList.remove("show");
        } catch (error) {
            alert("Lỗi: " + error.message);
        } finally {
            importCsvInput.value = "";
        }
    });
}

/* =========================================================
   NOTES MANAGEMENT LOGIC (LocalStorage persistent)
========================================================= */
const NOTES_STORAGE_KEY = "expense_tracker_user_notes";
let userNotes = [];
let editingNoteId = null;

const addNoteBtn = document.getElementById("add-note-btn");
const noteEditorCard = document.getElementById("note-editor-card");
const noteEditorTitle = document.getElementById("note-editor-title");
const noteForm = document.getElementById("note-form");
const noteTitleInput = document.getElementById("note-title-input");
const noteRichEditor = document.getElementById("note-rich-editor");
const noteTextColorInput = document.getElementById("note-text-color-input");
const noteFontSizeSelect = document.getElementById("note-fontsize-select");
const notePinnedInput = document.getElementById("note-pinned-input");
const noteCancelBtn = document.getElementById("note-cancel-btn");
const notesGridContainer = document.getElementById("notes-grid-container");
const notesEmptyState = document.getElementById("notes-empty-state");

// Rich Text Toolbar Actions
document.querySelectorAll(".note-rich-toolbar .toolbar-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
        e.preventDefault();
        const command = btn.getAttribute("data-command");
        if (command) {
            document.execCommand(command, false, null);
            if (noteRichEditor) noteRichEditor.focus();
        }
    });
});

if (noteFontSizeSelect) {
    noteFontSizeSelect.addEventListener("change", (e) => {
        const sizeVal = e.target.value;
        if (sizeVal) {
            document.execCommand("fontSize", false, sizeVal);
            if (noteRichEditor) noteRichEditor.focus();
        }
    });
}

if (noteTextColorInput) {
    noteTextColorInput.addEventListener("input", (e) => {
        const colorVal = e.target.value;
        if (colorVal) {
            document.execCommand("foreColor", false, colorVal);
            if (noteRichEditor) noteRichEditor.focus();
        }
    });
}

function loadNotesFromStorage() {
    try {
        const stored = localStorage.getItem(NOTES_STORAGE_KEY);
        if (stored) {
            userNotes = JSON.parse(stored);
        } else {
            // Default sample notes with rich HTML
            userNotes = [
                {
                    id: "note_1",
                    title: "Kế hoạch tiết kiệm tháng này",
                    contentHtml: "<p><strong>Mục tiêu:</strong> Dành ra ít nhất <u>20% thu nhập</u> chuyển vào Ví tiết kiệm đầu tháng ngay sau khi nhận lương.</p><ul><li>Hạn chế ăn ngoài quá 3 lần/tuần</li><li>Ghi chép chi tiêu mỗi ngày</li></ul>",
                    color: "pink",
                    pinned: true,
                    updatedAt: new Date().toLocaleDateString("vi-VN")
                },
                {
                    id: "note_2",
                    title: "Danh sách đồ cần mua sắp tới",
                    contentHtml: "<ol><li>Thay dầu xe máy định kỳ</li><li>Mua sắm nhu yếu phẩm siêu thị cuối tuần</li><li>Kiểm tra gia hạn gói Internet</li></ol>",
                    color: "gold",
                    pinned: false,
                    updatedAt: new Date().toLocaleDateString("vi-VN")
                }
            ];
            saveNotesToStorage();
        }
    } catch (e) {
        userNotes = [];
    }
    renderNotes();
}

function saveNotesToStorage() {
    try {
        localStorage.setItem(NOTES_STORAGE_KEY, JSON.stringify(userNotes));
    } catch (e) {
        console.error("Failed to save notes:", e);
    }
}

function renderNotes() {
    if (!notesGridContainer) return;
    notesGridContainer.innerHTML = "";

    if (userNotes.length === 0) {
        if (notesEmptyState) notesEmptyState.style.display = "block";
        return;
    }
    if (notesEmptyState) notesEmptyState.style.display = "none";

    // Sort: pinned notes first, then latest
    const sorted = [...userNotes].sort((a, b) => {
        if (a.pinned === b.pinned) return 0;
        return a.pinned ? -1 : 1;
    });

    sorted.forEach(note => {
        const card = document.createElement("div");
        card.className = `note-card color-${note.color || 'pink'} ${note.pinned ? 'is-pinned' : ''}`;

        if (note.pinned) {
            const pinIcon = document.createElement("div");
            pinIcon.className = "note-pin-badge";
            pinIcon.innerHTML = '<i class="fa-solid fa-thumbtack"></i>';
            card.appendChild(pinIcon);
        }

        const header = document.createElement("div");
        header.className = "note-card-header";
        const title = document.createElement("h3");
        title.className = "note-card-title";
        title.textContent = note.title;
        header.appendChild(title);

        const body = document.createElement("div");
        body.className = "note-card-body";
        // Render rich HTML content preserving formatting, fonts, colors, lists
        if (note.contentHtml) {
            body.innerHTML = note.contentHtml;
        } else if (note.content) {
            // Legacy plain text fallback
            body.textContent = note.content;
        }

        const footer = document.createElement("div");
        footer.className = "note-card-footer";

        const dateSpan = document.createElement("span");
        dateSpan.textContent = note.updatedAt || "Hôm nay";

        const actions = document.createElement("div");
        actions.className = "note-actions";

        // Pin button
        const pinBtn = document.createElement("button");
        pinBtn.type = "button";
        pinBtn.className = `note-btn pin ${note.pinned ? 'active' : ''}`;
        pinBtn.title = note.pinned ? "Bỏ ghim" : "Ghim lên đầu";
        pinBtn.innerHTML = `<i class="fa-${note.pinned ? 'solid' : 'regular'} fa-thumbtack"></i>`;
        pinBtn.addEventListener("click", () => togglePinNote(note.id));

        // Edit button
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "note-btn edit";
        editBtn.title = "Chỉnh sửa";
        editBtn.innerHTML = '<i class="fa-solid fa-pen-to-square"></i>';
        editBtn.addEventListener("click", () => openEditNote(note));

        // Delete button
        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "note-btn delete";
        delBtn.title = "Xóa ghi chú";
        delBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        delBtn.addEventListener("click", () => deleteNote(note.id));

        actions.appendChild(pinBtn);
        actions.appendChild(editBtn);
        actions.appendChild(delBtn);

        footer.appendChild(dateSpan);
        footer.appendChild(actions);

        card.appendChild(header);
        card.appendChild(body);
        card.appendChild(footer);

        notesGridContainer.appendChild(card);
    });
}

function openAddNote() {
    editingNoteId = null;
    noteForm.reset();
    if (noteRichEditor) noteRichEditor.innerHTML = "";
    const pinkRadio = document.querySelector('input[name="note-color"][value="pink"]');
    if (pinkRadio) pinkRadio.checked = true;
    notePinnedInput.checked = false;
    noteEditorTitle.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Thêm ghi chú mới';
    noteEditorCard.style.display = "block";
    noteTitleInput.focus();
}

function openEditNote(note) {
    editingNoteId = note.id;
    noteTitleInput.value = note.title;
    if (noteRichEditor) {
        noteRichEditor.innerHTML = note.contentHtml || (note.content ? note.content.replace(/\n/g, "<br>") : "");
    }
    const colorRadio = document.querySelector(`input[name="note-color"][value="${note.color || 'pink'}"]`);
    if (colorRadio) colorRadio.checked = true;
    notePinnedInput.checked = Boolean(note.pinned);
    noteEditorTitle.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Chỉnh sửa ghi chú';
    noteEditorCard.style.display = "block";
    noteTitleInput.focus();
}

function closeNoteEditor() {
    editingNoteId = null;
    noteForm.reset();
    if (noteRichEditor) noteRichEditor.innerHTML = "";
    noteEditorCard.style.display = "none";
}

function togglePinNote(id) {
    userNotes = userNotes.map(n => {
        if (n.id === id) {
            return { ...n, pinned: !n.pinned };
        }
        return n;
    });
    saveNotesToStorage();
    renderNotes();
}

function deleteNote(id) {
    if (!confirm("Bạn có chắc chắn muốn xóa ghi chú này?")) return;
    userNotes = userNotes.filter(n => n.id !== id);
    saveNotesToStorage();
    renderNotes();
}

if (addNoteBtn) {
    addNoteBtn.addEventListener("click", openAddNote);
}

if (noteCancelBtn) {
    noteCancelBtn.addEventListener("click", closeNoteEditor);
}

if (noteForm) {
    noteForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const title = noteTitleInput.value.trim();
        const contentHtml = noteRichEditor ? noteRichEditor.innerHTML.trim() : "";
        const selectedColor = document.querySelector('input[name="note-color"]:checked')?.value || "pink";
        const pinned = notePinnedInput.checked;

        if (!title || !contentHtml || contentHtml === "<br>") {
            alert("Vui lòng nhập cả tiêu đề và nội dung ghi chú.");
            return;
        }

        const dateStr = new Date().toLocaleDateString("vi-VN");

        if (editingNoteId) {
            userNotes = userNotes.map(n => {
                if (n.id === editingNoteId) {
                    return {
                        ...n,
                        title,
                        contentHtml,
                        color: selectedColor,
                        pinned,
                        updatedAt: dateStr
                    };
                }
                return n;
            });
        } else {
            const newNote = {
                id: "note_" + Date.now(),
                title,
                contentHtml,
                color: selectedColor,
                pinned,
                updatedAt: dateStr
            };
            userNotes.unshift(newNote);
        }

        saveNotesToStorage();
        renderNotes();
        closeNoteEditor();
    });
}

// Initialize Notes on page load
loadNotesFromStorage();

/* =========================================================
   DAY COUNTER LOGIC (Đếm ngày: Ngày đi làm vs Ngày thường)
========================================================= */
const COUNTER_STORAGE_KEY = "expense_tracker_day_counters";
let dayCounterEvents = [];

const rangeStartDateInput = document.getElementById("range-start-date");
const rangeEndDateInput = document.getElementById("range-end-date");
const calcWorkdaysResult = document.getElementById("calc-workdays-result");
const calcCalendardaysResult = document.getElementById("calc-calendardays-result");

const addCounterTargetBtn = document.getElementById("add-counter-target-btn");
const counterEditorCard = document.getElementById("counter-editor-card");
const counterForm = document.getElementById("counter-form");
const counterTitleInput = document.getElementById("counter-title-input");
const counterDateInput = document.getElementById("counter-date-input");
const counterModeSelect = document.getElementById("counter-mode-select");
const counterCancelBtn = document.getElementById("counter-cancel-btn");
const counterGridContainer = document.getElementById("counter-grid-container");
const counterEmptyState = document.getElementById("counter-empty-state");

/**
 * Calculates workdays (Monday-Friday) and total calendar days between two dates.
 * d1, d2 are Date objects.
 */
function calculateDaysDifference(d1, d2) {
    // Normalize dates to midnight
    const start = new Date(d1.getFullYear(), d1.getMonth(), d1.getDate());
    const end = new Date(d2.getFullYear(), d2.getMonth(), d2.getDate());

    const isNegative = end < start;
    const from = isNegative ? end : start;
    const to = isNegative ? start : end;

    const oneDay = 24 * 60 * 60 * 1000;
    const totalCalendarDays = Math.round((to - from) / oneDay);

    let workdays = 0;
    const cur = new Date(from);
    // Iterate day by day from start to end (excluding start, or inclusive counting standard)
    while (cur < to) {
        cur.setDate(cur.getDate() + 1);
        const dayOfWeek = cur.getDay(); // 0 = Sunday, 6 = Saturday
        if (dayOfWeek !== 0 && dayOfWeek !== 6) {
            workdays++;
        }
    }

    return {
        calendarDays: totalCalendarDays,
        workdays: workdays,
        isNegative: isNegative
    };
}

function updateQuickRangeCalc() {
    if (!rangeStartDateInput || !rangeEndDateInput) return;

    const startVal = rangeStartDateInput.value;
    const endVal = rangeEndDateInput.value;

    if (!startVal || !endVal) {
        if (calcWorkdaysResult) calcWorkdaysResult.textContent = "0";
        if (calcCalendardaysResult) calcCalendardaysResult.textContent = "0";
        return;
    }

    const d1 = new Date(startVal);
    const d2 = new Date(endVal);

    const diff = calculateDaysDifference(d1, d2);

    if (calcWorkdaysResult) {
        calcWorkdaysResult.textContent = `${diff.workdays} ngày`;
    }
    if (calcCalendardaysResult) {
        calcCalendardaysResult.textContent = `${diff.calendarDays} ngày`;
    }
}

// Initial defaults for quick range calculator: Today -> Next month same day
const todayObj = new Date();
const todayFormatted = todayObj.toISOString().split("T")[0];
const nextMonthObj = new Date();
nextMonthObj.setMonth(nextMonthObj.getMonth() + 1);
const nextMonthFormatted = nextMonthObj.toISOString().split("T")[0];

if (rangeStartDateInput) rangeStartDateInput.value = todayFormatted;
if (rangeEndDateInput) rangeEndDateInput.value = nextMonthFormatted;
updateQuickRangeCalc();

if (rangeStartDateInput) rangeStartDateInput.addEventListener("change", updateQuickRangeCalc);
if (rangeEndDateInput) rangeEndDateInput.addEventListener("change", updateQuickRangeCalc);

function loadCounterEventsFromStorage() {
    try {
        const stored = localStorage.getItem(COUNTER_STORAGE_KEY);
        if (stored) {
            dayCounterEvents = JSON.parse(stored);
        } else {
            // Default samples
            const endOfYear = `${new Date().getFullYear()}-12-31`;
            dayCounterEvents = [
                {
                    id: "event_1",
                    title: "Kết thúc năm " + new Date().getFullYear(),
                    targetDate: endOfYear,
                    mode: "workday"
                }
            ];
            saveCounterEventsToStorage();
        }
    } catch (e) {
        dayCounterEvents = [];
    }
    renderCounterEvents();
}

function saveCounterEventsToStorage() {
    try {
        localStorage.setItem(COUNTER_STORAGE_KEY, JSON.stringify(dayCounterEvents));
    } catch (e) {
        console.error("Failed to save counter events:", e);
    }
}

function renderCounterEvents() {
    if (!counterGridContainer) return;
    counterGridContainer.innerHTML = "";

    if (dayCounterEvents.length === 0) {
        if (counterEmptyState) counterEmptyState.style.display = "block";
        return;
    }
    if (counterEmptyState) counterEmptyState.style.display = "none";

    const today = new Date();
    const todayMidnight = new Date(today.getFullYear(), today.getMonth(), today.getDate());

    dayCounterEvents.forEach(evt => {
        const target = new Date(evt.targetDate);
        const targetMidnight = new Date(target.getFullYear(), target.getMonth(), target.getDate());

        const diff = calculateDaysDifference(todayMidnight, targetMidnight);

        let statusText = "";
        let statusClass = "";

        if (targetMidnight > todayMidnight) {
            statusText = `Còn ${diff.calendarDays} ngày nữa`;
            statusClass = "future";
        } else if (targetMidnight < todayMidnight) {
            statusText = `Đã qua ${diff.calendarDays} ngày`;
            statusClass = "past";
        } else {
            statusText = "Hôm nay là ngày mốc!";
            statusClass = "today";
        }

        const card = document.createElement("div");
        card.className = "counter-card";

        const formattedTargetDate = target.toLocaleDateString("vi-VN", {
            weekday: "long",
            year: "numeric",
            month: "long",
            day: "numeric"
        });

        card.innerHTML = `
            <div class="counter-card-header">
                <div>
                    <h3 class="counter-card-title">${escapeHtml(evt.title)}</h3>
                    <div style="font-size: 12px; color: var(--sakura-plum-soft); margin-top: 3px;">
                        <i class="fa-regular fa-calendar"></i> ${formattedTargetDate}
                    </div>
                </div>
                <span class="counter-card-status-badge ${statusClass}">${statusText}</span>
            </div>

            <div class="counter-card-stats">
                <div class="counter-stat-item workday">
                    <span class="counter-stat-label"><i class="fa-solid fa-briefcase"></i> Ngày đi làm</span>
                    <span class="counter-stat-val">${diff.workdays}</span>
                    <span style="font-size: 11px; color: #528e71;">(Bỏ T7 & CN)</span>
                </div>
                <div class="counter-stat-item calendar">
                    <span class="counter-stat-label"><i class="fa-solid fa-calendar-days"></i> Ngày thường</span>
                    <span class="counter-stat-val">${diff.calendarDays}</span>
                    <span style="font-size: 11px; color: var(--sakura-plum-soft);">(Tất cả các ngày)</span>
                </div>
            </div>

            <div class="counter-card-footer">
                <span style="font-size: 11.5px; color: var(--sakura-plum-soft);">
                    <i class="fa-solid fa-tag"></i> Ưu tiên: ${evt.mode === 'workday' ? 'Ngày đi làm' : 'Ngày thường'}
                </span>
                <button type="button" class="note-btn delete" title="Xóa sự kiện" data-event-id="${evt.id}">
                    <i class="fa-solid fa-trash"></i>
                </button>
            </div>
        `;

        const deleteBtn = card.querySelector(`[data-event-id="${evt.id}"]`);
        if (deleteBtn) {
            deleteBtn.addEventListener("click", () => deleteCounterEvent(evt.id));
        }

        counterGridContainer.appendChild(card);
    });
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
}

function deleteCounterEvent(id) {
    if (!confirm("Bạn có chắc muốn xóa mốc sự kiện này?")) return;
    dayCounterEvents = dayCounterEvents.filter(e => e.id !== id);
    saveCounterEventsToStorage();
    renderCounterEvents();
}

if (addCounterTargetBtn) {
    addCounterTargetBtn.addEventListener("click", () => {
        counterForm.reset();
        if (counterDateInput) counterDateInput.value = todayFormatted;
        if (counterEditorCard) {
            counterEditorCard.style.display = counterEditorCard.style.display === "none" ? "block" : "none";
        }
    });
}

if (counterCancelBtn) {
    counterCancelBtn.addEventListener("click", () => {
        if (counterEditorCard) counterEditorCard.style.display = "none";
    });
}

if (counterForm) {
    counterForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const title = counterTitleInput.value.trim();
        const targetDate = counterDateInput.value;
        const mode = counterModeSelect.value;

        if (!title || !targetDate) return;

        const newEvt = {
            id: "counter_" + Date.now(),
            title: title,
            targetDate: targetDate,
            mode: mode
        };

        dayCounterEvents.unshift(newEvt);
        saveCounterEventsToStorage();
        renderCounterEvents();

        counterForm.reset();
        if (counterEditorCard) counterEditorCard.style.display = "none";
    });
}

// Load events on initialize
loadCounterEventsFromStorage();


/* =========================================================
   FLOATING MINI CALCULATOR LOGIC
========================================================= */
const calcToggleBtn = document.getElementById("calc-toggle-btn");
const miniCalcCard = document.getElementById("mini-calculator-card");
const calcCloseBtn = document.getElementById("calc-close-btn");
const calcMinimizeBtn = document.getElementById("calc-minimize-btn");
const calcDisplay = document.getElementById("calc-display");
const calcHistory = document.getElementById("calc-history");

let calcCurrentValue = "0";
let calcPreviousValue = null;
let calcCurrentOp = null;
let calcResetOnNext = false;

function updateCalcScreen() {
    if (calcDisplay) {
        // Format thousands with comma if valid number
        const num = parseFloat(calcCurrentValue);
        if (!isNaN(num) && calcCurrentValue.indexOf(".") === -1 && Math.abs(num) < 1e14) {
            calcDisplay.textContent = num.toLocaleString("en-US");
        } else {
            calcDisplay.textContent = calcCurrentValue;
        }
    }
}

function handleCalcNumber(digit) {
    if (calcResetOnNext) {
        calcCurrentValue = digit === "000" ? "0" : digit;
        calcResetOnNext = false;
    } else {
        if (digit === "000") {
            if (calcCurrentValue !== "0") {
                calcCurrentValue += "000";
            }
        } else {
            if (calcCurrentValue === "0") {
                calcCurrentValue = digit;
            } else {
                if (calcCurrentValue.length < 14) {
                    calcCurrentValue += digit;
                }
            }
        }
    }
    updateCalcScreen();
}

function handleCalcDecimal() {
    if (calcResetOnNext) {
        calcCurrentValue = "0.";
        calcResetOnNext = false;
    } else if (!calcCurrentValue.includes(".")) {
        calcCurrentValue += ".";
    }
    updateCalcScreen();
}

function handleCalcAction(action) {
    if (action === "clear") {
        calcCurrentValue = "0";
        calcPreviousValue = null;
        calcCurrentOp = null;
        calcResetOnNext = false;
        if (calcHistory) calcHistory.textContent = "";
        updateCalcScreen();
        return;
    }

    if (action === "backspace") {
        if (calcResetOnNext) return;
        if (calcCurrentValue.length > 1) {
            calcCurrentValue = calcCurrentValue.slice(0, -1);
        } else {
            calcCurrentValue = "0";
        }
        updateCalcScreen();
        return;
    }

    if (action === "percent") {
        const val = parseFloat(calcCurrentValue);
        if (!isNaN(val)) {
            calcCurrentValue = (val / 100).toString();
            updateCalcScreen();
        }
        return;
    }

    if (["add", "subtract", "multiply", "divide"].includes(action)) {
        const opSymbols = { add: "+", subtract: "−", multiply: "×", divide: "÷" };
        const currentNum = parseFloat(calcCurrentValue);

        if (calcPreviousValue !== null && calcCurrentOp && !calcResetOnNext) {
            // Compute intermediate result
            const res = computeMath(calcPreviousValue, currentNum, calcCurrentOp);
            calcPreviousValue = res;
            calcCurrentValue = res.toString();
            updateCalcScreen();
        } else {
            calcPreviousValue = currentNum;
        }

        calcCurrentOp = action;
        calcResetOnNext = true;
        if (calcHistory) {
            calcHistory.textContent = `${calcPreviousValue.toLocaleString("en-US")} ${opSymbols[action]}`;
        }
        return;
    }

    if (action === "calculate") {
        if (calcPreviousValue === null || !calcCurrentOp) return;
        const currentNum = parseFloat(calcCurrentValue);
        const opSymbols = { add: "+", subtract: "−", multiply: "×", divide: "÷" };
        const res = computeMath(calcPreviousValue, currentNum, calcCurrentOp);

        if (calcHistory) {
            calcHistory.textContent = `${calcPreviousValue.toLocaleString("en-US")} ${opSymbols[calcCurrentOp]} ${currentNum.toLocaleString("en-US")} =`;
        }

        calcCurrentValue = res.toString();
        calcPreviousValue = null;
        calcCurrentOp = null;
        calcResetOnNext = true;
        updateCalcScreen();
    }
}

function computeMath(a, b, op) {
    let result = 0;
    switch (op) {
        case "add":
            result = a + b;
            break;
        case "subtract":
            result = a - b;
            break;
        case "multiply":
            result = a * b;
            break;
        case "divide":
            result = b === 0 ? 0 : a / b;
            break;
    }
    // Round to avoid floating precision issues
    return Math.round(result * 100000000) / 100000000;
}

if (calcToggleBtn && miniCalcCard) {
    calcToggleBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        miniCalcCard.classList.toggle("show");
    });
}

if (calcCloseBtn && miniCalcCard) {
    calcCloseBtn.addEventListener("click", () => {
        miniCalcCard.classList.remove("show");
    });
}

// Calculator keypad click events (Supports both .c-key and .calc-btn)
document.querySelectorAll(".c-key, .calc-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
        e.preventDefault();
        const num = btn.getAttribute("data-num");
        const action = btn.getAttribute("data-action");

        if (num !== null) {
            handleCalcNumber(num);
        } else if (action === "decimal") {
            handleCalcDecimal();
        } else if (action) {
            handleCalcAction(action);
        }
    });
});