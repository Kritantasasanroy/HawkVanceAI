/// What each action costs, in one place.
///
/// Credits exist because raw token counts are not something a person can plan around: the number
/// moves with the length of a document they did not write and a reply they did not choose, so a
/// remaining balance tells them nothing about how many more questions they have. A fixed price per
/// action does.
///
/// The ledger underneath still records real tokens and real cost, so billing and admin reporting
/// stay accurate. Credits are what the user is shown and what is enforced.
export type BillableAction =
  | 'question'
  | 'documentScanQuick'
  | 'documentScanNormal'
  | 'documentScanThorough'
  | 'chatSummary';

export class CreditCost {
  /// Work that runs on the user's own machine is free, because charging for electricity they
  /// already paid for would be dishonest. That is why a chat summary costs nothing: it is produced
  /// by the local model and never leaves the computer.
  private static readonly rates: Readonly<Record<BillableAction, number>> = {
    question: 1,
    documentScanQuick: 1,
    documentScanNormal: 2,
    documentScanThorough: 3,
    chatSummary: 0,
  };

  static of(action: BillableAction): number {
    return CreditCost.rates[action];
  }

  /// The whole table, for the screen that explains the pricing to the user. Returned as a copy so a
  /// caller cannot quietly reprice an action by mutating it.
  static table(): Readonly<Record<BillableAction, number>> {
    return { ...CreditCost.rates };
  }

  /// A failed request costs nothing.
  ///
  /// The attempt is still recorded, because a silent gap in the ledger is worse than a zero row,
  /// but nobody should pay for an answer they did not receive.
  static readonly failure = 0;
}
