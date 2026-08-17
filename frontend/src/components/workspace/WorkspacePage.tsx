import React from "react";

type WorkspacePageProps = {
  eyebrow: string;
  title: string;
  description: string;
  split?: boolean;
  sidePanel?: React.ReactNode;
  children: React.ReactNode;
};

export const WorkspacePage: React.FC<WorkspacePageProps> = ({
  eyebrow,
  title,
  description,
  split = false,
  sidePanel,
  children,
}) => {
  if (split) {
    return (
      <section className="workspace-page workspace-page-split">
        <main className="workspace-main">
          <WorkspacePageHeader eyebrow={eyebrow} title={title} description={description} />
          {children}
        </main>
        {sidePanel}
      </section>
    );
  }

  return (
    <section className="workspace-page">
      <WorkspacePageHeader eyebrow={eyebrow} title={title} description={description} />
      {children}
    </section>
  );
};

function WorkspacePageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <header className="workspace-page-header">
      <div>
        <p className="product-eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </header>
  );
}
