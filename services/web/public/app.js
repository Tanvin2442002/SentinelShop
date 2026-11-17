// SentinelShop static page. Talks to catalog-api through the edge at /api
// (the edge, or the Traefik ingress in Kubernetes, strips the /api prefix).
//
// Security notes:
// - Server data is only ever written with textContent, never innerHTML, so a
//   product name like <script> is shown as text, not run.
// - The login token is kept in a variable only (not localStorage): no endpoint
//   needs it yet, and storage would outlive the tab for any injected script.
// - Shoppers see friendly messages only. Raw status codes, API details and
//   trace ids are internal: operators find them in the logs, not on the page.
"use strict";

const API = "/api";
const POLL_INTERVAL_MS = 1000;
// The worker takes 1-2 s per order; 30 s covers a queue backlog in the demo.
const POLL_LIMIT_MS = 30000;
const SEARCH_DELAY_MS = 300;
const LOW_STOCK = 20;

let session = null; // {username, token, expiresAt}
let sessionTimer = null;
const orders = []; // orders placed in this tab, newest first: {id, name, quantity, status}

// --- helpers ---------------------------------------------------------------

// Calls the API and returns {ok, status, data}. Never throws for HTTP errors;
// a network failure comes back as status 0.
async function api(method, path, body) {
  const options = { method, headers: { Accept: "application/json" } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(API + path, options);
  } catch (err) {
    return { ok: false, status: 0, data: null };
  }
  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    data = null;
  }
  return { ok: response.ok, status: response.status, data };
}

// Turns a failed call into a sentence for a shopper. The API's own "detail"
// text is not shown: it is written for developers and can change.
function friendlyError(result, action) {
  switch (result.status) {
    case 0: return "We can't reach the shop right now. Check your connection and try again.";
    case 401: return "That username and password don't match. Please try again.";
    case 403: return "This request was blocked. Please try again later.";
    case 404: return action === "order" ? "We couldn't find that order." : "That product is no longer available.";
    case 422: return "Some of the details look wrong. Please check them and try again.";
    case 429: return "Too many attempts. Please wait a moment and try again.";
    case 503: return "Our ordering system is busy. Please try again in a moment.";
    default: return "Something went wrong on our side. Please try again.";
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

function formatPrice(value) {
  return "$" + Number(value).toFixed(2);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// --- toasts ----------------------------------------------------------------

const toasts = document.getElementById("toasts");

function toast(message, kind) {
  const item = el("div", "toast" + (kind ? " " + kind : ""), message);
  toasts.append(item);
  setTimeout(() => {
    item.classList.add("leaving");
    setTimeout(() => item.remove(), 250);
  }, 4000);
}

// --- views (hash routing: #shop and #login) --------------------------------

const viewShop = document.getElementById("view-shop");
const viewLogin = document.getElementById("view-login");

function showView() {
  const onLogin = location.hash === "#login" && !session;
  viewShop.hidden = onLogin;
  viewLogin.hidden = !onLogin;
  if (onLogin) {
    document.getElementById("login-user").focus();
  } else if (location.hash === "#login") {
    // Already signed in: the login page has nothing to offer.
    location.hash = "#shop";
  }
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", showView);

// --- product artwork -------------------------------------------------------

// A picture for each seeded product, picked by a word in its name. Unknown
// products get their first letter, so new rows still look intentional.
const PRODUCT_ICONS = [
  ["mouse", "🖱️"], ["keyboard", "⌨️"], ["hub", "🔌"], ["monitor", "🖥️"],
  ["webcam", "📷"], ["stand", "💻"], ["headset", "🎧"], ["ssd", "💾"],
  ["lamp", "💡"], ["chair", "🪑"], ["cable", "🔗"], ["power", "🔋"],
];

function productIcon(name) {
  const lower = name.toLowerCase();
  for (const [word, icon] of PRODUCT_ICONS) {
    if (lower.includes(word)) return icon;
  }
  return name.charAt(0).toUpperCase();
}

// --- products and search ---------------------------------------------------

const grid = document.getElementById("products-grid");
const productsStatus = document.getElementById("products-status");
const emptyBox = document.getElementById("products-empty");
const emptyText = document.getElementById("products-empty-text");
const searchInput = document.getElementById("search-q");
const searchClear = document.getElementById("search-clear");

function stockBadge(stock) {
  if (stock <= 0) return el("span", "badge badge-bad", "Out of stock");
  if (stock < LOW_STOCK) return el("span", "badge badge-warn", "Only " + stock + " left");
  return el("span", "badge badge-ok", "In stock");
}

function renderSkeleton() {
  grid.replaceChildren();
  for (let i = 0; i < 8; i++) {
    const card = el("div", "card skeleton");
    card.setAttribute("aria-hidden", "true");
    const body = el("div", "card-body");
    body.append(el("div", "skeleton-line"), el("div", "skeleton-line short"));
    card.append(el("div", "card-art"), body);
    grid.append(card);
  }
}

function quantityStepper(product) {
  const wrap = el("div", "stepper");
  const minus = el("button", "", "−");
  minus.type = "button";
  minus.setAttribute("aria-label", "Fewer");
  // Same limits as the API (quantity 1..100), so most bad input never leaves the page.
  const input = el("input");
  input.type = "number";
  input.min = "1";
  input.max = String(Math.min(100, Math.max(1, product.stock)));
  input.step = "1";
  input.value = "1";
  input.inputMode = "numeric";
  input.setAttribute("aria-label", "Quantity of " + product.name);
  const plus = el("button", "", "+");
  plus.type = "button";
  plus.setAttribute("aria-label", "More");

  const change = (delta) => {
    const next = (Number(input.value) || 1) + delta;
    input.value = String(Math.min(Number(input.max), Math.max(1, next)));
  };
  minus.addEventListener("click", () => change(-1));
  plus.addEventListener("click", () => change(1));
  // Nothing to choose when the product is sold out.
  minus.disabled = plus.disabled = input.disabled = product.stock <= 0;
  wrap.append(minus, input, plus);
  return { wrap, input };
}

function productCard(product, index) {
  const card = el("article", "card");
  const art = el("div", "card-art tone-" + (index % 5), productIcon(product.name));
  art.setAttribute("aria-hidden", "true");

  const body = el("div", "card-body");
  const meta = el("div", "card-meta");
  meta.append(el("span", "price", formatPrice(product.price)), stockBadge(product.stock));

  const actions = el("div", "card-actions");
  const { wrap, input } = quantityStepper(product);
  const buy = el("button", "btn btn-primary", product.stock > 0 ? "Order" : "Sold out");
  buy.type = "button";
  buy.disabled = product.stock <= 0;
  buy.addEventListener("click", () => placeOrder(product, input, buy));
  actions.append(wrap, buy);

  body.append(el("h3", "card-name", product.name), meta, actions);
  card.append(art, body);
  return card;
}

let loadCounter = 0;

async function loadProducts(query) {
  // A slower earlier request must not overwrite the results of a newer one.
  const thisLoad = ++loadCounter;
  const path = query ? "/search?q=" + encodeURIComponent(query) : "/products";
  renderSkeleton();
  emptyBox.hidden = true;
  productsStatus.textContent = "";
  searchClear.hidden = !query;

  const result = await api("GET", path);
  if (thisLoad !== loadCounter) return;

  if (!result.ok || !Array.isArray(result.data)) {
    grid.replaceChildren();
    emptyBox.hidden = false;
    emptyText.textContent = friendlyError(result, "products");
    return;
  }
  grid.replaceChildren(...result.data.map(productCard));
  if (result.data.length === 0) {
    emptyBox.hidden = false;
    emptyText.textContent = "No products match “" + query + "”. Try another word.";
  }
  const count = result.data.length + (result.data.length === 1 ? " item" : " items");
  productsStatus.textContent = query ? count + " for “" + query + "”" : count;
}

let searchTimer = null;

document.getElementById("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  clearTimeout(searchTimer);
  if (location.hash === "#login") location.hash = "#shop";
  loadProducts(searchInput.value.trim());
});

// Search as you type, but wait for a pause so each key press is not a request.
searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadProducts(searchInput.value.trim()), SEARCH_DELAY_MS);
});

searchClear.addEventListener("click", () => {
  searchInput.value = "";
  loadProducts("");
});

// --- orders ----------------------------------------------------------------

const ordersList = document.getElementById("orders-list");
const ordersEmpty = document.getElementById("orders-empty");

const STATUS_VIEW = {
  PENDING: { label: "Order placed", badge: "badge-info", step: "step-1" },
  PROCESSING: { label: "Processing", badge: "badge-warn", step: "step-2" },
  COMPLETED: { label: "Completed", badge: "badge-ok", step: "step-3 done" },
  FAILED: { label: "Failed", badge: "badge-bad", step: "step-3 failed" },
};

function orderItem(order) {
  const view = STATUS_VIEW[order.status] || STATUS_VIEW.PENDING;
  const item = el("li", "order-item");
  const top = el("div", "order-top");
  top.append(el("span", "order-title", "Order #" + order.id), el("span", "badge " + view.badge, view.label));
  const sub = el("p", "order-sub", order.quantity + " × " + order.name);
  const progress = el("div", "progress " + view.step);
  progress.setAttribute("aria-hidden", "true");
  progress.append(el("span"), el("span"), el("span"));
  item.append(top, sub, progress);
  return item;
}

function renderOrders() {
  ordersList.replaceChildren(...orders.map(orderItem));
  ordersEmpty.hidden = orders.length > 0;
}

async function placeOrder(product, quantityInput, button) {
  const quantity = Number(quantityInput.value);
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > 100) {
    toast("Please choose a quantity from 1 to 100.", "error");
    return;
  }
  button.disabled = true;
  const label = button.textContent;
  button.textContent = "Ordering…";
  try {
    // product_id and quantity are sent as JSON numbers: the API is strict and
    // rejects "1" (string) with 422.
    const result = await api("POST", "/orders", { product_id: product.id, quantity });
    if (!result.ok) {
      toast(friendlyError(result, "place"), "error");
      return;
    }
    const order = { id: result.data.id, name: product.name, quantity, status: result.data.status || "PENDING" };
    orders.unshift(order);
    renderOrders();
    toast("Order #" + order.id + " placed: " + quantity + " × " + product.name, "ok");
    quantityInput.value = "1";
    followOrder(order);
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

// Polls GET /orders/{id} until COMPLETED or FAILED (or the time limit).
async function followOrder(order) {
  const started = Date.now();
  while (Date.now() - started < POLL_LIMIT_MS) {
    await sleep(POLL_INTERVAL_MS);
    const result = await api("GET", "/orders/" + encodeURIComponent(order.id));
    if (!result.ok) continue; // a blip; try again on the next tick
    if (result.data.status !== order.status) {
      order.status = result.data.status;
      renderOrders();
    }
    if (order.status === "COMPLETED") {
      toast("Order #" + order.id + " is complete.", "ok");
      return;
    }
    if (order.status === "FAILED") {
      toast("Order #" + order.id + " could not be completed.", "error");
      return;
    }
  }
}

const lookupResult = document.getElementById("lookup-result");

document.getElementById("order-lookup").addEventListener("submit", async (event) => {
  event.preventDefault();
  const orderId = Number(document.getElementById("order-id").value);
  lookupResult.hidden = false;
  if (!Number.isInteger(orderId) || orderId < 1) {
    lookupResult.replaceChildren(el("p", "form-error", "Order numbers are whole numbers, like 12."));
    return;
  }
  const result = await api("GET", "/orders/" + encodeURIComponent(orderId));
  if (!result.ok) {
    lookupResult.replaceChildren(el("p", "form-error", friendlyError(result, "order")));
    return;
  }
  const known = orders.find((o) => o.id === result.data.id);
  const name = known ? known.name : "product " + result.data.product_id;
  lookupResult.replaceChildren(orderItem({ ...result.data, name }));
});

// --- login -----------------------------------------------------------------

const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const loginSubmit = document.getElementById("login-submit");
const userInput = document.getElementById("login-user");
const passwordInput = document.getElementById("login-pass");
const togglePass = document.getElementById("toggle-pass");

function showLoginError(message) {
  loginError.textContent = message;
  loginError.hidden = !message;
}

function renderAccount() {
  const signedIn = Boolean(session);
  document.getElementById("signin-link").hidden = signedIn;
  document.getElementById("user-chip").hidden = !signedIn;
  if (signedIn) {
    document.getElementById("user-name").textContent = session.username;
    document.getElementById("user-avatar").textContent = session.username.charAt(0);
  }
}

function signOut(message) {
  session = null;
  clearTimeout(sessionTimer);
  renderAccount();
  if (message) toast(message);
}

togglePass.addEventListener("click", () => {
  const show = passwordInput.type === "password";
  passwordInput.type = show ? "text" : "password";
  togglePass.textContent = show ? "Hide" : "Show";
  togglePass.setAttribute("aria-pressed", String(show));
  togglePass.setAttribute("aria-label", show ? "Hide password" : "Show password");
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = userInput.value.trim();
  const password = passwordInput.value;
  userInput.parentElement.classList.toggle("invalid", !username);
  passwordInput.closest(".field").classList.toggle("invalid", !password);
  if (!username || !password) {
    showLoginError("Please enter your username and password.");
    return;
  }

  showLoginError("");
  loginSubmit.disabled = true;
  loginSubmit.classList.add("loading");
  const result = await api("POST", "/login", { username, password });
  loginSubmit.disabled = false;
  loginSubmit.classList.remove("loading");
  // Clear the password field whatever the outcome.
  passwordInput.value = "";

  if (!result.ok) {
    session = null;
    showLoginError(friendlyError(result, "login"));
    passwordInput.focus();
    return;
  }
  session = {
    username,
    token: result.data.token,
    expiresAt: Date.now() + result.data.expires_in * 1000,
  };
  // Sign out in the page when the token expires, so the header never lies.
  clearTimeout(sessionTimer);
  sessionTimer = setTimeout(() => signOut("Your session has expired. Please sign in again."), result.data.expires_in * 1000);
  renderAccount();
  loginForm.reset();
  toast("Welcome back, " + username + "!", "ok");
  location.hash = "#shop";
});

document.getElementById("signout").addEventListener("click", () => signOut("You have been signed out."));

// --- start -----------------------------------------------------------------

renderAccount();
renderOrders();
showView();
loadProducts("");
