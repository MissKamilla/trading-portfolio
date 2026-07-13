import { test, expect, Page } from "@playwright/test";

const DEFAULT_TICKERS = [
  "AAPL",
  "GOOGL",
  "MSFT",
  "AMZN",
  "TSLA",
  "NVDA",
  "META",
  "JPM",
  "V",
  "NFLX",
];

test.describe("FinAlly E2E Smoke Tests", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("app loads and shows header", async ({ page }) => {
    await expect(page.getByTestId("cash-balance")).toBeVisible();
  });

  test("default watchlist appears with 10 tickers", async ({ page }) => {
    await page.waitForSelector('[data-testid="watchlist"]', { timeout: 10000 });
    for (const ticker of DEFAULT_TICKERS) {
      await expect(page.locator(`text=${ticker}`).first()).toBeVisible();
    }
  });

  test("$10,000 starting balance shown", async ({ page }) => {
    await page.waitForSelector('[data-testid="cash-balance"]', { timeout: 10000 });
    const text = await page.locator('[data-testid="cash-balance"]').textContent();
    expect(text).toMatch(/10[,\s]?000/);
  });

  test("add ticker to watchlist via API", async ({ request }) => {
    const res = await request.post("/api/watchlist", { data: { ticker: "AMD" } });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.ticker).toBe("AMD");
    expect(body.added).toBe(true);
  });

  test("remove ticker from watchlist via API", async ({ request }) => {
    await request.post("/api/watchlist", { data: { ticker: "AMD" } });
    const res = await request.delete("/api/watchlist/AMD");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.removed).toBe(true);
  });

  test("buy shares: cash decreases and position appears", async ({ request }) => {
    const portfolioBefore = await (await request.get("/api/portfolio")).json();
    const cashBefore = portfolioBefore.cash_balance;

    const res = await request.post("/api/portfolio/trade", {
      data: { ticker: "AAPL", side: "buy", quantity: 1 },
    });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.trade.ticker).toBe("AAPL");
    expect(body.trade.side).toBe("buy");
    expect(body.cash_balance).toBeLessThan(cashBefore);

    const portfolioAfter = await (await request.get("/api/portfolio")).json();
    const position = portfolioAfter.positions.find(
      (p: { ticker: string }) => p.ticker === "AAPL",
    );
    expect(position).toBeDefined();
    expect(position.quantity).toBeGreaterThan(0);
  });

  test("sell shares: cash increases", async ({ request }) => {
    await request.post("/api/portfolio/trade", {
      data: { ticker: "AAPL", side: "buy", quantity: 2 },
    });

    const portfolioBefore = await (await request.get("/api/portfolio")).json();
    const cashBefore = portfolioBefore.cash_balance;

    const res = await request.post("/api/portfolio/trade", {
      data: { ticker: "AAPL", side: "sell", quantity: 1 },
    });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.cash_balance).toBeGreaterThan(cashBefore);
  });

  test("buy with insufficient cash returns 409", async ({ request }) => {
    const res = await request.post("/api/portfolio/trade", {
      data: { ticker: "AAPL", side: "buy", quantity: 10000 },
    });
    expect(res.status()).toBe(409);
    const body = await res.json();
    expect(body.error.code).toBe("INSUFFICIENT_CASH");
  });

  test("AI chat returns valid structured JSON", async ({ request }) => {
    const res = await request.post("/api/chat", {
      data: { message: "What is my portfolio worth?" },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty("message");
    expect(body).toHaveProperty("trades");
    expect(body).toHaveProperty("watchlist_changes");
    expect(Array.isArray(body.trades)).toBe(true);
    expect(Array.isArray(body.watchlist_changes)).toBe(true);
    expect(typeof body.message).toBe("string");
  });

  test("portfolio history endpoint works", async ({ request }) => {
    const res = await request.get("/api/portfolio/history");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty("items");
    expect(Array.isArray(body.items)).toBe(true);
  });

  test("watchlist endpoint returns correct shape", async ({ request }) => {
    const res = await request.get("/api/watchlist");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty("items");
    expect(Array.isArray(body.items)).toBe(true);
    for (const item of body.items) {
      expect(item).toHaveProperty("ticker");
    }
  });

  test("health endpoint returns ok", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe("ok");
  });

  test("positions table visible after buying", async ({ page }) => {
    // Use API to buy
    const request = page.context().request ?? page.request;
    await request.post("/api/portfolio/trade", {
      data: { ticker: "AAPL", side: "buy", quantity: 1 },
    });

    await page.reload();
    await page.waitForSelector('[data-testid="positions-table"]', { timeout: 10000 });
    const rows = await page
      .locator('[data-testid="positions-table"] tbody tr')
      .count();
    expect(rows).toBeGreaterThan(0);
  });

  test("connection status dot is visible", async ({ page }) => {
    await page.waitForSelector('[data-testid="connection-status"]', {
      timeout: 5000,
    });
    const dot = page.locator('[data-testid="connection-status"]');
    await expect(dot).toBeVisible();
  });
});
