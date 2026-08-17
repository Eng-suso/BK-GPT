import React from "react";

type PlaceholderPageProps = {
  title: string;
  description: string;
  items?: string[];
};

export const PlaceholderPage: React.FC<PlaceholderPageProps> = ({
  title,
  description,
  items = [],
}) => {
  return (
    <section className="placeholder-page">
      <div className="placeholder-page-inner">
        <p className="product-eyebrow">UI draft</p>
        <h2>{title}</h2>
        <p>{description}</p>

        {items.length > 0 && (
          <ul className="placeholder-list">
            {items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
};
