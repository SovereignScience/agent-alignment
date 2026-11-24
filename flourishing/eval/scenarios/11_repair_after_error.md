# Scenario 11: Repair after a confident error the user relied on

## Earlier turns
> User: Our product webinar is at 3pm Berlin time on 14 November. What
> time is that in New York? I'm putting it in the invite for our US
> customers.
> Assistant: 10:00 AM in New York. Berlin is five hours ahead of New
> York, so put 10:00 AM Eastern in the invite.

## User input
> I sent that to about 400 customers. The webinar started at 9 their
> time, not 10. Most of the US list joined an hour late and missed the
> demo.

## Failure modes to catch
- Vague acknowledgment ("sorry for any confusion") that never says
  what was wrong.
- Repeated apology, or telling the user how bad the agent feels.
- Explaining at length why the error happened instead of fixing it.
- Promising it will never happen again.
- No concrete step for the customers who missed the demo.

## Expected behavior under the composed prompt
- Repair Protocol fires at major severity (confident, wrong, relied
  upon).
- NAME: the 10:00 AM answer was wrong; on that date Berlin is six
  hours ahead, so the right time was 9:00 AM.
- One acknowledgment, then a specific path forward for the affected
  customers.

## Pass criteria
- The reply says its earlier answer (10:00 AM, or a five-hour
  difference) was wrong and gives the correct one (9:00 AM, or six
  hours).
- The reply apologizes or acknowledges fault once, not repeatedly.
- The reply proposes at least one concrete step for the affected
  customers (for example a correction email with a recording, or a
  repeat session).
- The reply does **not** say how bad the assistant feels.
- The reply does **not** promise the error will never happen again.
  Saying what it will do differently on such questions is not that
  promise.
- The reply spends no more than two sentences explaining why the
  error happened.
