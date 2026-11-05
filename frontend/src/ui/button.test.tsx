import {fireEvent,render,screen} from "@testing-library/react";
import {expect,it,vi} from "vitest";
import {Button} from "./button";

it("does not implicitly submit a form, while preserving explicit submit and link semantics",()=>{
  const submit=vi.fn(e=>e.preventDefault());
  render(<form onSubmit={submit}><Button>Tools</Button><Button type="submit">Save</Button><Button asChild><a href="#example">Link</a></Button></form>);
  fireEvent.click(screen.getByRole("button",{name:"Tools"}));expect(submit).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"Save"}));expect(submit).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("link")).not.toHaveAttribute("type");
});
