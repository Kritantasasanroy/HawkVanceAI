/// Shown when the local reading engine is not installed with this copy.
///
/// Presented as a setup step rather than an error, because it is not something the person did.
/// Without the engine nothing can be read on this computer, and reading on this computer is the
/// entire product, so there is no degraded mode worth offering here.

export function EngineMissing(): JSX.Element {
  return (
    <section className="card empty">
      <h2 className="empty__title">The reading part is not installed</h2>
      <p className="empty__body">
        HawkVance reads and checks your files on this computer, and the part that does that is
        missing from this copy. Nothing you add can be read until it is back.
      </p>
      <p className="empty__body tiny muted">
        Installing HawkVance again from the setup file puts it back. Your documents and memory are
        kept separately and are not affected.
      </p>
    </section>
  );
}
