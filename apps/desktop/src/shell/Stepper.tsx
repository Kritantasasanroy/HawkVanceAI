/// Shows where somebody is in a multi-step job, and what is still coming.
///
/// The document flow changed its whole screen at each stage with no indication that a stage
/// existed, so people could not tell whether the app was mid-way through something, finished, or
/// broken. Naming the steps up front costs one row and answers all three.

export type Step = { readonly id: string; readonly label: string; readonly detail: string };

export function Stepper({
  steps,
  currentId,
}: {
  readonly steps: ReadonlyArray<Step>;
  readonly currentId: string;
}): JSX.Element {
  const currentIndex = steps.findIndex((step) => step.id === currentId);

  return (
    <ol className="stepper" aria-label="Progress">
      {steps.map((step, index) => {
        const state = index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'todo';
        return (
          <li
            key={step.id}
            className={`stepper__step stepper__step--${state}`}
            aria-current={state === 'current' ? 'step' : undefined}
          >
            <span className="stepper__marker" aria-hidden>
              {state === 'done' ? '✓' : index + 1}
            </span>
            <span className="stepper__text">
              <strong>{step.label}</strong>
              <span className="tiny">{step.detail}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
