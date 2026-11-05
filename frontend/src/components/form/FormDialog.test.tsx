import {act,fireEvent,render,screen} from "@testing-library/react";
import {expect,it,vi} from "vitest";
import {FormDialog} from "./FormDialog";

it("coalesces repeated submissions until the current handler finishes, then allows retry",async()=>{
  let finish=()=>{};const submit=vi.fn(()=>new Promise<void>(r=>{finish=r;}));
  render(<FormDialog open onOpenChange={()=>{}} title="Record" submitLabel="Save" isSubmitting={false} onSubmit={submit}><input aria-label="Name"/></FormDialog>);
  const form=screen.getByRole("button",{name:"Save"}).closest("form")!;
  fireEvent.submit(form);fireEvent.submit(form);expect(submit).toHaveBeenCalledTimes(1);
  await act(async()=>{finish();});fireEvent.submit(form);expect(submit).toHaveBeenCalledTimes(2);
  await act(async()=>{finish();});
});
