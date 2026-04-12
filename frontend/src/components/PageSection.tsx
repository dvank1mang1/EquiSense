import { ReactNode } from "react";
import clsx from "clsx";

type PageSectionProps = {
  id: string;
  title: string;
  eyebrow?: string;
  children: ReactNode;
  className?: string;
  /** Без оболочки card — только заголовок + контент */
  bare?: boolean;
};

export default function PageSection({
  id,
  title,
  eyebrow,
  children,
  className,
  bare,
}: PageSectionProps) {
  const inner = (
    <>
      {eyebrow ? <p className="section-title-accent mb-1.5">{eyebrow}</p> : null}
      <h2 id={id} className="mb-4 text-lg font-semibold tracking-tight text-white md:text-xl">
        {title}
      </h2>
      {children}
    </>
  );

  if (bare) {
    return (
      <section className={className} aria-labelledby={id}>
        {inner}
      </section>
    );
  }

  return (
    <section
      className={clsx(
        "card ring-1 ring-surface-700/40 shadow-md shadow-black/10",
        className,
      )}
      aria-labelledby={id}
    >
      {inner}
    </section>
  );
}
