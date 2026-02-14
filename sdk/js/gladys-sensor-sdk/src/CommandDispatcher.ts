import { ComponentState } from "./generated/common";
import { Command } from "./generated/orchestrator";
import {
  type StartArgs,
  type StopArgs,
  type RecoverArgs,
  type HealthCheckArgs,
  type CommandArgs,
  parseStartArgs,
  parseStopArgs,
  parseRecoverArgs,
  parseHealthCheckArgs,
} from "./args";

/**
 * Handler function for commands with typed arguments.
 * Return null/undefined for default state transition.
 * Return explicit ComponentState to override default.
 * Throw to set ERROR state (except HEALTH_CHECK).
 */
export type CommandHandler<TArgs extends CommandArgs> = (
  args: TArgs
) => Promise<ComponentState | null | void> | ComponentState | null | void;

/**
 * Handler function for simple commands (PAUSE, RESUME, RELOAD).
 * No arguments passed.
 */
export type SimpleCommandHandler = () =>
  | Promise<ComponentState | null | void>
  | ComponentState | null | void;

/**
 * Global error handler for command failures.
 * Called when any command handler throws exception.
 * Return null to accept ERROR state.
 * Return explicit ComponentState to override.
 */
export type CommandErrorHandler = (
  command: Command,
  error: Error,
  currentState: ComponentState
) => ComponentState | null | void;

/**
 * Result of dispatching a command.
 */
export interface DispatchResult {
  /** State after command execution */
  state: ComponentState;
  /** Error message if handler threw, undefined otherwise */
  errorMessage?: string;
}

/** Default state transitions per command. */
const DEFAULT_TRANSITIONS: ReadonlyMap<Command, ComponentState> = new Map([
  [Command.COMMAND_START, ComponentState.COMPONENT_STATE_ACTIVE],
  [Command.COMMAND_STOP, ComponentState.COMPONENT_STATE_STOPPED],
  [Command.COMMAND_PAUSE, ComponentState.COMPONENT_STATE_PAUSED],
  [Command.COMMAND_RESUME, ComponentState.COMPONENT_STATE_ACTIVE],
  [Command.COMMAND_RELOAD, ComponentState.COMPONENT_STATE_ACTIVE],
  [Command.COMMAND_RECOVER, ComponentState.COMPONENT_STATE_ACTIVE],
]);

/**
 * Fluent command handler registration and dispatch.
 * Routes commands to typed handlers with automatic state management.
 *
 * @example
 * ```typescript
 * const dispatcher = new CommandDispatcher()
 *   .onStart(async (args) => {
 *     await initialize(args.dryRun);
 *     return null; // Default: ACTIVE
 *   })
 *   .onStop(async (args) => {
 *     await cleanup(args.force);
 *     return null; // Default: STOPPED
 *   });
 * ```
 */
export class CommandDispatcher {
  private handlers = new Map<Command, (args?: Record<string, unknown>) => Promise<ComponentState | null | void>>();
  private errorHandler: CommandErrorHandler | null = null;
  private state: ComponentState = ComponentState.COMPONENT_STATE_UNKNOWN;

  /** Register START command handler. Default transition: -> ACTIVE */
  onStart(handler: CommandHandler<StartArgs>): this {
    this.handlers.set(Command.COMMAND_START, async (raw) => {
      return handler(parseStartArgs(raw));
    });
    return this;
  }

  /** Register STOP command handler. Default transition: -> STOPPED */
  onStop(handler: CommandHandler<StopArgs>): this {
    this.handlers.set(Command.COMMAND_STOP, async (raw) => {
      return handler(parseStopArgs(raw));
    });
    return this;
  }

  /** Register PAUSE command handler. Default transition: -> PAUSED */
  onPause(handler: SimpleCommandHandler): this {
    this.handlers.set(Command.COMMAND_PAUSE, async () => {
      return handler();
    });
    return this;
  }

  /** Register RESUME command handler. Default transition: -> ACTIVE */
  onResume(handler: SimpleCommandHandler): this {
    this.handlers.set(Command.COMMAND_RESUME, async () => {
      return handler();
    });
    return this;
  }

  /** Register RELOAD command handler. Default transition: -> ACTIVE */
  onReload(handler: SimpleCommandHandler): this {
    this.handlers.set(Command.COMMAND_RELOAD, async () => {
      return handler();
    });
    return this;
  }

  /** Register HEALTH_CHECK command handler. State unchanged on success or failure. */
  onHealthCheck(handler: CommandHandler<HealthCheckArgs>): this {
    this.handlers.set(Command.COMMAND_HEALTH_CHECK, async (raw) => {
      return handler(parseHealthCheckArgs(raw));
    });
    return this;
  }

  /** Register RECOVER command handler. Default transition: -> ACTIVE */
  onRecover(handler: CommandHandler<RecoverArgs>): this {
    this.handlers.set(Command.COMMAND_RECOVER, async (raw) => {
      return handler(parseRecoverArgs(raw));
    });
    return this;
  }

  /** Register global error handler for all commands. */
  onCommandError(handler: CommandErrorHandler): this {
    this.errorHandler = handler;
    return this;
  }

  /**
   * Dispatch a command with optional args.
   * Handles state transitions, error handling, and HEALTH_CHECK special case.
   *
   * @param command Command enum value
   * @param args Raw args from PendingCommand (plain object)
   * @returns DispatchResult with resulting state and optional error message
   */
  async dispatch(
    command: Command,
    args?: Record<string, unknown>
  ): Promise<DispatchResult> {
    const handler = this.handlers.get(command);
    const previousState = this.state;
    const isHealthCheck = command === Command.COMMAND_HEALTH_CHECK;

    if (!handler) {
      return {
        state: this.state,
        errorMessage: `No handler registered for ${command}`,
      };
    }

    try {
      const result = await handler(args);

      if (result !== null && result !== undefined) {
        // Handler returned explicit state override
        this.state = result;
      } else {
        // Apply default transition (HEALTH_CHECK has no default = state unchanged)
        const defaultState = DEFAULT_TRANSITIONS.get(command);
        if (defaultState !== undefined) {
          this.state = defaultState;
        }
      }

      return { state: this.state };
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));

      if (isHealthCheck) {
        // HEALTH_CHECK exception: state unchanged, no ERROR
        this.state = previousState;

        if (this.errorHandler) {
          this.errorHandler(command, error, previousState);
        }

        return { state: this.state, errorMessage: error.message };
      }

      // All other commands: set ERROR state
      this.state = ComponentState.COMPONENT_STATE_ERROR;

      if (this.errorHandler) {
        const overrideState = this.errorHandler(command, error, previousState);
        if (overrideState !== null && overrideState !== undefined) {
          this.state = overrideState;
        }
      }

      return { state: this.state, errorMessage: error.message };
    }
  }

  /** Get current component state. */
  getState(): ComponentState {
    return this.state;
  }

  /** Set component state (for test setup or manual override). */
  setState(state: ComponentState): void {
    this.state = state;
  }
}
