/**
 * Error boundary.
 *
 * A render error in the map must not blank the whole page. Errors explain what
 * happened and offer the way forward — they do not apologize or go vague.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Names the region that failed, so the message can be specific. */
  region: string;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[${this.props.region}] render failed`, error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="boundary" role="alert">
        <p className="boundary__title">The {this.props.region} stopped working.</p>
        <p className="boundary__detail">{this.state.error.message}</p>
        <button
          className="boundary__action"
          onClick={() => this.setState({ error: null })}
        >
          Try again
        </button>
      </div>
    );
  }
}
