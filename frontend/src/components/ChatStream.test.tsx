import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatStream } from "@/components/ChatStream";
import type { ChatTurn } from "@/components/ChatStream";
import { HIGH_FINAL, FALLBACK_FINAL, MOTOR_TOC } from "@/test/fixtures";

function turn(overrides: Partial<ChatTurn>): ChatTurn {
  return {
    id: "turn_1",
    query: "What is the warranty period?",
    answerText: "",
    streaming: false,
    phase: "streaming",
    final: null,
    error: null,
    ...overrides,
  };
}

describe("ChatStream (FR-007, FR-008, FR-011, FR-012, FR-018)", () => {
  it("renders the user query and the completed answer with all insight blocks", () => {
    const turns: ChatTurn[] = [
      turn({ answerText: HIGH_FINAL.answer, final: HIGH_FINAL }),
    ];
    render(<ChatStream turns={turns} toc={MOTOR_TOC} />);

    expect(screen.getByText("What is the warranty period?")).toBeInTheDocument();
    expect(screen.getByText(HIGH_FINAL.answer)).toBeInTheDocument();
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuetext", "HIGH, 0.94");
    expect(screen.getByText("Warranty & Support")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /why did you look here/i })).toBeInTheDocument();
  });

  it("shows the fallback banner and no-citations note for a fallback answer", () => {
    const turns: ChatTurn[] = [
      turn({ id: "turn_2", answerText: FALLBACK_FINAL.answer, final: FALLBACK_FINAL }),
    ];
    render(<ChatStream turns={turns} toc={MOTOR_TOC} />);

    const alerts = screen.getAllByRole("alert");
    expect(alerts.length).toBeGreaterThan(0);
    expect(screen.getByText(/no section citations/i)).toBeInTheDocument();
  });

  it("surfaces a mid-stream error as an alert without dropping the partial answer", () => {
    const turns: ChatTurn[] = [
      turn({
        id: "turn_3",
        answerText: "Partial answer ",
        error: {
          type: "about:blank",
          title: "Internal Server Error",
          status: 500,
          code: "INTERNAL_ERROR",
          detail: "Generation failed mid-stream.",
        },
      }),
    ];
    render(<ChatStream turns={turns} toc={MOTOR_TOC} />);

    expect(screen.getByText("Partial answer")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("INTERNAL_ERROR");
  });
});
