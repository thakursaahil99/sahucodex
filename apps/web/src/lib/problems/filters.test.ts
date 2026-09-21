import { describe, expect, it } from "vitest";

import {
  DEFAULT_FILTERS,
  effectiveSort,
  filtersToApiQuery,
  filtersToSearchParams,
  hasActiveFilters,
  parseFilters,
} from "@/lib/problems/filters";

const parse = (query: string) => parseFilters(new URLSearchParams(query));

describe("parseFilters (the URL is untrusted input)", () => {
  it("returns the defaults for an empty query", () => {
    expect(parse("")).toEqual(DEFAULT_FILTERS);
  });

  it("reads every supported filter", () => {
    expect(parse("q=graph&difficulty=EASY&difficulty=HARD&tag=trie&tag=graph&status=solved&acceptance=mid&sort=title&page=3")).toEqual({
      q: "graph",
      difficulties: ["EASY", "HARD"],
      tags: ["trie", "graph"],
      status: "solved",
      acceptance: "mid",
      sort: "title",
      page: 3,
    });
  });

  it("discards invalid values instead of passing them to the API", () => {
    const filters = parse("difficulty=IMPOSSIBLE&difficulty=EASY&tag=Not%20A%20Slug&tag=ok-tag&status=deleted&acceptance=huge&sort=drop-table&page=-4");
    expect(filters.difficulties).toEqual(["EASY"]);
    expect(filters.tags).toEqual(["ok-tag"]);
    expect(filters.status).toBe("");
    expect(filters.acceptance).toBe("");
    expect(filters.sort).toBe("newest");
    expect(filters.page).toBe(1);
  });

  it("caps hostile sizes", () => {
    const tags = Array.from({ length: 50 }, (_, i) => `tag=t${i}`).join("&");
    expect(parse(tags).tags).toHaveLength(10);
    expect(parse(`q=${"x".repeat(500)}`).q).toHaveLength(100);
    expect(parse("page=99999999999").page).toBe(1);
    expect(parse("page=abc").page).toBe(1);
  });

  it("de-duplicates repeated tags", () => {
    expect(parse("tag=a&tag=a&tag=b").tags).toEqual(["a", "b"]);
  });
});

describe("filtersToSearchParams", () => {
  it("omits defaults so links stay short", () => {
    expect(filtersToSearchParams(DEFAULT_FILTERS).toString()).toBe("");
  });

  it("round-trips through parseFilters", () => {
    const original = parse("q=heap&difficulty=MEDIUM&tag=heap&status=unsolved&acceptance=low&sort=acceptance&page=2");
    expect(parseFilters(filtersToSearchParams(original))).toEqual(original);
  });
});

describe("filtersToApiQuery", () => {
  it("always sends paging and a sort", () => {
    const query = new URLSearchParams(filtersToApiQuery(DEFAULT_FILTERS));
    expect(query.get("page")).toBe("1");
    expect(query.get("limit")).toBe("20");
    expect(query.get("sort")).toBe("newest");
  });

  it("maps acceptance buckets to min/max percentages", () => {
    const low = new URLSearchParams(filtersToApiQuery({ ...DEFAULT_FILTERS, acceptance: "low" }));
    expect([low.get("min_acceptance"), low.get("max_acceptance")]).toEqual([null, "30"]);
    const mid = new URLSearchParams(filtersToApiQuery({ ...DEFAULT_FILTERS, acceptance: "mid" }));
    expect([mid.get("min_acceptance"), mid.get("max_acceptance")]).toEqual(["30", "60"]);
    const high = new URLSearchParams(filtersToApiQuery({ ...DEFAULT_FILTERS, acceptance: "high" }));
    expect([high.get("min_acceptance"), high.get("max_acceptance")]).toEqual(["60", null]);
  });

  it("repeats multi-value filters", () => {
    const query = new URLSearchParams(
      filtersToApiQuery({ ...DEFAULT_FILTERS, difficulties: ["EASY", "HARD"], tags: ["a", "b"] }),
    );
    expect(query.getAll("difficulty")).toEqual(["EASY", "HARD"]);
    expect(query.getAll("tag")).toEqual(["a", "b"]);
  });

  it("properly encodes search text", () => {
    const query = filtersToApiQuery({ ...DEFAULT_FILTERS, q: "a&b=c #1" });
    expect(new URLSearchParams(query).get("q")).toBe("a&b=c #1");
    expect(query).not.toContain("a&b");
  });
});

describe("effectiveSort", () => {
  it("ranks a text search by relevance unless another order was chosen", () => {
    expect(effectiveSort({ ...DEFAULT_FILTERS, q: "graph" })).toBe("relevance");
    expect(effectiveSort({ ...DEFAULT_FILTERS, q: "graph", sort: "title" })).toBe("title");
  });
  it("cannot sort by relevance without a query", () => {
    expect(effectiveSort({ ...DEFAULT_FILTERS, sort: "relevance" })).toBe("newest");
  });
});

describe("hasActiveFilters", () => {
  it("ignores sort and page", () => {
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, sort: "title", page: 4 })).toBe(false);
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, tags: ["x"] })).toBe(true);
  });
});
