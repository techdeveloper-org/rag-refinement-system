import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExplainabilityPanel } from "@/components/ExplainabilityPanel";
import { HIGH_ROUTING, MOTOR_TOC } from "@/test/fixtures";

describe("ExplainabilityPanel (FR-012)", () => {
  it("is a collapsed disclosure by default", () => {
    render(<ExplainabilityPanel routing={HIGH_ROUTING} toc={MOTOR_TOC} />);
    const trigger = screen.getByRole("button", { name: /why did you look here/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("expands to show rationale and the TOC-joined considered sections", async () => {
    render(<ExplainabilityPanel routing={HIGH_ROUTING} toc={MOTOR_TOC} />);
    const trigger = screen.getByRole("button", { name: /why did you look here/i });
    await userEvent.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/only section semantically matching/i)).toBeInTheDocument();

    expect(screen.getByText("Warranty & Support")).toBeInTheDocument();
    expect(screen.getByText("Maintenance")).toBeInTheDocument();
    expect(screen.getByText("Installation")).toBeInTheDocument();

    expect(screen.getByText("0.94")).toBeInTheDocument();
    expect(screen.getByText("0.31")).toBeInTheDocument();
  });

  it("lists both selected and rejected sections", async () => {
    render(<ExplainabilityPanel routing={HIGH_ROUTING} toc={MOTOR_TOC} />);
    await userEvent.click(screen.getByRole("button", { name: /why did you look here/i }));
    expect(screen.getByText("selected")).toBeInTheDocument();
    expect(screen.getAllByText("rejected")).toHaveLength(2);
  });
});
