// SentinelShop static page. Talks to catalog-api through the edge at /api
// (the edge, or the Traefik ingress in Kubernetes, strips the /api prefix).
//
// Security notes:
// - Server data is only ever written with textContent, never innerHTML, so a
//   product name like <script> is shown as text, not run.
// - The login token is kept in a variable only (not localStorage): no endpoint
//   needs it yet, and storage would outlive the tab for any injected script.
"use strict";

const API = "/api";
const POLL_INTERVAL_MS = 1000;
// The worker takes 1-2 s per order; 30 s covers a queue backlog in the demo.
const POLL_LIMIT_MS = 30000;
const FINAL_STATUSES = ["COMPLETED", "FAILED"];

let session = null; // {username, token, expiresAt}

// --- helpers ---------------------------------------------------------------

// Calls the API and returns {ok, status, data, traceId}. Never throws for
// HTTP errors; a network failure comes back as status 0.
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
    return { ok: false, status: 0, data: { detail: "network error, is the stack up?" }, traceId: "" };
  }
  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    data = { detail: "unexpected reply (HTTP " + response.status + ")" };
  }
  return {
    ok: response.ok,
    status: response.status,
    data,
    traceId: response.headers.get("X-Trace-Id") || "",
  };
}

// Contract errors are {"detail": "<text>"}.
function errorText(result) {
  const detail = result.data && typeof result.data.detail === "string" ? result.data.detail : "request failed";
  return result.status ? "Error " + result.status + ": " + detail : detail;
}

function setStatus(element, text, kind, traceId) {
  element.replaceChildren();
  element.className = "status" + (kind ? " " + kind : "");
  element.append(document.createTextNode(text));
  if (traceId) {
    const trace = document.createElement("span");
    trace.className = "trace";
    trace.textContent = " (trace " + traceId + ")";
    element.append(trace);
  }
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = String(text);
  return td;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// --- products and search ---------------------------------------------------

const productsBody = document.getElementById("products-body");
const productsStatus = document.getElementById("products-status");
const orderStatus = document.getElementById("order-status");

function renderProducts(products) {
  productsBody.replaceChildren();
  for (const product of products) {
    const row = document.createElement("tr");
    row.append(cell(product.id), cell(product.name), cell(Number(product.price).toFixed(2)), cell(product.stock));

    // Same limits as the API (quantity 1..100), so most bad input never leaves the page.
    const quantity = document.createElement("input");
    quantity.type = "number";
    quantity.min = "1";
    quantity.max = "100";
    quantity.step = "1";
    quantity.value = "1";
    quantity.setAttribute("aria-label", "Quantity of " + product.name);
    const qtyCell = document.createElement("td");
    qtyCell.append(quantity);

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Order";
    button.addEventListener("click", () => placeOrder(product, quantity, button));
    const buttonCell = document.createElement("td");
    buttonCell.append(button);

    row.append(qtyCell, buttonCell);
    productsBody.append(row);
  }
}

async function loadProducts(query) {
  const path = query ? "/search?q=" + encodeURIComponent(query) : "/products";
  setStatus(productsStatus, "Loading...");
  const result = await api("GET", path);
  if (!result.ok) {
    productsBody.replaceChildren();
    setStatus(productsStatus, errorText(result), "error", result.traceId);
    return;
  }
  renderProducts(result.data);
  const label = query ? result.data.length + " match(es) for \"" + query + "\"" : result.data.length + " products";
  setStatus(productsStatus, label, "", result.traceId);
}

document.getElementById("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const query = document.getElementById("search-q").value.trim();
  loadProducts(query);
});

document.getElementById("search-clear").addEventListener("click", () => {
  document.getElementById("search-q").value = "";
  loadProducts("");
});

// --- orders ----------------------------------------------------------------

async function placeOrder(product, quantityInput, button) {
  const quantity = Number(quantityInput.value);
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > 100) {
    setStatus(orderStatus, "Quantity must be a whole number from 1 to 100.", "error");
    return;
  }
  button.disabled = true;
  try {
    // product_id and quantity are sent as JSON numbers: the API is strict and
    // rejects "1" (string) with 422.
    const result = await api("POST", "/orders", { product_id: product.id, quantity });
    if (!result.ok) {
      setStatus(orderStatus, "Order for " + product.name + " failed. " + errorText(result), "error", result.traceId);
      return;
    }
    document.getElementById("order-id").value = result.data.id;
    await followOrder(result.data.id, result.traceId);
  } finally {
    button.disabled = false;
  }
}

// Polls GET /orders/{id} until COMPLETED or FAILED (or the time limit).
async function followOrder(orderId, traceId) {
  const started = Date.now();
  let status = "PENDING";
  while (Date.now() - started < POLL_LIMIT_MS) {
    setStatus(orderStatus, "Order #" + orderId + ": " + status, "", traceId);
    await sleep(POLL_INTERVAL_MS);
    const result = await api("GET", "/orders/" + encodeURIComponent(orderId));
    if (!result.ok) {
      setStatus(orderStatus, "Order #" + orderId + ": could not read status. " + errorText(result), "error", traceId);
      return;
    }
    status = result.data.status;
    if (FINAL_STATUSES.includes(status)) {
      setStatus(orderStatus, "Order #" + orderId + ": " + status, status === "COMPLETED" ? "ok" : "error", traceId);
      return;
    }
  }
  setStatus(orderStatus, "Order #" + orderId + ": still " + status + " after 30 s (queue backlog?)", "error", traceId);
}

document.getElementById("order-lookup").addEventListener("submit", async (event) => {
  event.preventDefault();
  const orderId = Number(document.getElementById("order-id").value);
  if (!Number.isInteger(orderId) || orderId < 1) {
    setStatus(orderStatus, "Order id must be a positive whole number.", "error");
    return;
  }
  const result = await api("GET", "/orders/" + encodeURIComponent(orderId));
  if (!result.ok) {
    setStatus(orderStatus, "Order #" + orderId + ": " + errorText(result), "error", result.traceId);
    return;
  }
  const order = result.data;
  setStatus(orderStatus, "Order #" + order.id + ": " + order.status + " (product " + order.product_id + ", quantity " + order.quantity + ")",
    order.status === "COMPLETED" ? "ok" : order.status === "FAILED" ? "error" : "", result.traceId);
});

// --- login -----------------------------------------------------------------

const loginForm = document.getElementById("login-form");
const loginStatus = document.getElementById("login-status");

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = document.getElementById("login-user").value;
  const passwordInput = document.getElementById("login-pass");
  const result = await api("POST", "/login", { username, password: passwordInput.value });
  // Clear the password field whatever the outcome.
  passwordInput.value = "";
  if (!result.ok) {
    session = null;
    setStatus(loginStatus, errorText(result), "error", result.traceId);
    return;
  }
  session = {
    username,
    token: result.data.token,
    expiresAt: Date.now() + result.data.expires_in * 1000,
  };
  setStatus(loginStatus, "Logged in as " + username + " (token valid for " + result.data.expires_in + " s)", "ok", result.traceId);
});

loadProducts("");
