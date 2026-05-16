"""ModelDNA v2 - pipeline orchestrator (optional convenience).

Runs the data pipeline end to end. Each step is also runnable on its own;
this just chains them. Both inference and scoring are resumable, so it is
safe to rerun after an interruption.

  python run_pipeline.py            # inference -> scoring
  python run_pipeline.py --load     # inference -> scoring -> Snowflake load
  python run_pipeline.py --fallback # also write data/*.csv fallbacks

Snowflake load is kept opt-in because it needs schema.sql to have been run.
"""
import sys
import time

import inference
import score


def main():
    args = set(sys.argv[1:])
    t0 = time.time()

    print("\n=== STEP 1/2: inference ===")
    inference.run_inference()

    print("\n=== STEP 2/2: scoring ===")
    score.run_scoring()

    if "--fallback" in args:
        print("\n=== fallback CSVs ===")
        import precompute_fallback
        precompute_fallback.main()

    if "--load" in args:
        print("\n=== Snowflake load ===")
        import load_snowflake
        load_snowflake.load_all()
    else:
        print("\nNext: run schema.sql in Snowflake, then "
              "`python load_snowflake.py`, then `streamlit run dashboard.py`.")

    print(f"\nPipeline finished in {(time.time() - t0) / 60:.1f} min.")


if __name__ == "__main__":
    main()
