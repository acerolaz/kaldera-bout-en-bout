import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import * as matchers from "vitest-axe/matchers";
import { afterEach, expect } from "vitest";

expect.extend(matchers);
// Sans `globals`, Testing Library ne démonte pas seul le DOM entre deux tests.
afterEach(cleanup);
